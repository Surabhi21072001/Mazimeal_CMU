#!/usr/bin/env python3
"""
Match ingredient names to USDA FoodData Central (SR Legacy) and write their
per-100g nutrition.

    python3 scripts/match_usda.py <sr_legacy_folder> --names names.txt --review matches.csv --dry-run
    python3 scripts/match_usda.py <sr_legacy_folder> --names names.txt -o schema/seed/usda_nutrition.sql

<sr_legacy_folder> is the unzipped "FoodData Central SR Legacy CSV" download
(food.csv, nutrient.csv, food_nutrient.csv, food_portion.csv inside).
--names is one ingredient name per line (see scripts/ingredient_names.sh).

Output SQL sets usda_fdc_id, food_category and typical_serving_g on the
matching ingredients row and upserts ingredient_nutrition for every nutrient
in nutrients_master that has a usda_nutrient_code. Idempotent.

The review CSV lists every match with its score. Anything under --min-score
is written to the CSV but left out of the SQL. Check the CSV; fuzzy matching
gets the common ingredients right and the odd ones wrong.

Needs pandas and rapidfuzz.
"""
import argparse, csv, os, re, sys
from collections import defaultdict

try:
    import pandas as pd
    from rapidfuzz import fuzz, process
except ImportError:
    sys.exit("needs pandas and rapidfuzz: pip install pandas rapidfuzz")

# nutrient_id -> USDA nutrient_nbr, same as nutrients_master.usda_nutrient_code
NUTRIENTS = {
    "Energy": "208", "Macro_Protein": "203", "Macro_Fat": "204", "Macro_Carbohydrate": "205",
    "Fiber": "291", "Calcium": "301", "Iron": "303", "Magnesium": "304", "Phosphorus": "305",
    "Potassium": "306", "Sodium": "307", "Zinc": "309", "Copper": "312", "Selenium": "317",
    "Vitamin_A": "320", "Vitamin_D": "328", "Vitamin_E": "323", "Vitamin_K": "430",
    "Vitamin_C": "401", "Thiamin": "404", "Riboflavin": "405", "Niacin": "406",
    "Vitamin_B6": "415", "Folate": "435", "Vitamin_B12": "418",
    "Saturated_Fat": "606", "Sugar": "269", "Cholesterol": "601",
}
UNITS = {"KCAL": "kcal", "G": "g", "MG": "mg", "UG": "mcg", "IU": "IU"}

# Recipe wording -> how SR Legacy says it. Applied whole-phrase, longest first.
ALIASES = {
    "garbanzo beans": "chickpeas garbanzo beans mature seeds canned", "chickpea": "chickpeas garbanzo beans mature seeds canned", "icing sugar": "sugars powdered",
    "powdered sugar": "sugars powdered", "confectioners sugar": "sugars powdered",
    "brown sugar": "sugars brown", "sugar": "sugars granulated", "white sugar": "sugars granulated",
    "green onions": "onions spring", "green onion": "onions spring", "scallions": "onions spring",
    "spring onions": "onions spring", "cilantro": "coriander leaves raw", "coriander": "coriander leaves raw",
    "all-purpose flour": "wheat flour white all-purpose", "flour": "wheat flour white all-purpose",
    "plain flour": "wheat flour white all-purpose", "bread flour": "wheat flour white bread",
    "whole wheat flour": "wheat flour whole-grain", "cornstarch": "cornstarch", "corn starch": "cornstarch",
    "bell pepper": "peppers sweet green raw", "green pepper": "peppers sweet green raw",
    "red pepper": "peppers sweet red raw", "red bell pepper": "peppers sweet red raw",
    "jalapeno": "peppers jalapeno raw", "jalapenos": "peppers jalapeno raw",
    "chili powder": "spices chili powder", "cayenne": "spices pepper red or cayenne",
    "cayenne pepper": "spices pepper red or cayenne", "crushed red pepper flakes": "spices pepper red or cayenne",
    "dry crushed red pepper": "spices pepper red or cayenne", "red pepper flakes": "spices pepper red or cayenne",
    "black pepper": "spices pepper black", "pepper": "spices pepper black", "white pepper": "spices pepper white",
    "salt": "salt table", "kosher salt": "salt table", "sea salt": "salt table", "garlic salt": "spices garlic powder",
    "garlic powder": "spices garlic powder", "onion powder": "spices onion powder",
    "cumin": "spices cumin seed", "ground cumin": "spices cumin seed", "paprika": "spices paprika",
    "oregano": "spices oregano dried", "dried oregano": "spices oregano dried", "basil": "spices basil dried",
    "dried basil": "spices basil dried", "fresh basil": "basil fresh", "thyme": "spices thyme dried",
    "dried thyme": "spices thyme dried", "rosemary": "spices rosemary dried", "parsley": "parsley fresh",
    "fresh parsley": "parsley fresh", "dried parsley": "parsley dried", "bay leaf": "spices bay leaf",
    "bay leaves": "spices bay leaf", "cinnamon": "spices cinnamon ground", "ground cinnamon": "spices cinnamon ground",
    "nutmeg": "spices nutmeg ground", "ginger": "ginger root raw", "fresh ginger": "ginger root raw",
    "ground ginger": "spices ginger ground", "allspice": "spices allspice ground", "cloves": "spices cloves ground",
    "curry powder": "spices curry powder", "turmeric": "spices turmeric ground", "ground mustard": "spices mustard seed ground",
    "dry mustard": "spices mustard seed ground", "italian seasoning": "spices oregano dried",
    "vanilla": "vanilla extract", "vanilla extract": "vanilla extract",
    "baking soda": "leavening agents baking soda", "baking powder": "leavening agents baking powder double-acting",
    "yeast": "leavening agents yeast bakers active dry", "active dry yeast": "leavening agents yeast bakers active dry",
    "olive oil": "oil olive salad or cooking", "extra virgin olive oil": "oil olive salad or cooking",
    "vegetable oil": "oil canola", "canola oil": "oil canola", "oil": "oil canola", "sesame oil": "oil sesame salad or cooking",
    "shortening": "shortening household lard and vegetable oil",
    "butter": "butter salted", "unsalted butter": "butter without salt", "margarine": "margarine regular 80% fat stick",
    "egg": "egg whole raw fresh", "eggs": "egg whole raw fresh", "egg white": "egg white raw fresh",
    "egg whites": "egg white raw fresh", "egg yolk": "egg yolk raw fresh", "egg yolks": "egg yolk raw fresh",
    "milk": "milk whole", "whole milk": "milk whole", "skim milk": "milk nonfat", "buttermilk": "milk buttermilk fluid",
    "heavy cream": "cream fluid heavy whipping", "whipping cream": "cream fluid heavy whipping",
    "half-and-half": "cream fluid half and half", "sour cream": "cream sour cultured",
    "cream cheese": "cheese cream", "cheddar cheese": "cheese cheddar", "sharp cheddar cheese": "cheese cheddar",
    "mozzarella cheese": "cheese mozzarella whole milk", "parmesan cheese": "cheese parmesan grated",
    "swiss cheese": "cheese swiss", "feta cheese": "cheese feta", "monterey jack cheese": "cheese monterey",
    "cottage cheese": "cheese cottage creamed", "ricotta cheese": "cheese ricotta whole milk",
    "american cheese": "cheese pasteurized process american", "velveeta cheese": "cheese pasteurized process american",
    "yogurt": "yogurt plain whole milk", "plain yogurt": "yogurt plain whole milk", "greek yogurt": "yogurt greek plain whole milk",
    "chicken breast": "chicken broilers or fryers breast meat only raw", "chicken breasts": "chicken broilers or fryers breast meat only raw",
    "boneless skinless chicken breasts": "chicken broilers or fryers breast meat only raw",
    "boneless skinless chicken breast": "chicken broilers or fryers breast meat only raw",
    "chicken breast fillets": "chicken broilers or fryers breast meat only raw",
    "chicken thighs": "chicken broilers or fryers thigh meat only raw", "boneless skinless chicken thighs": "chicken broilers or fryers thigh meat only raw",
    "chicken": "chicken broilers or fryers meat only raw", "chicken wings": "chicken broilers or fryers wing meat and skin raw",
    "ground beef": "beef ground 85% lean meat 15% fat raw", "lean ground beef": "beef ground 90% lean meat 10% fat raw",
    "extra lean ground beef": "beef ground 95% lean meat 5% fat raw", "ground turkey": "turkey ground raw",
    "ground pork": "pork ground raw", "bacon": "pork cured bacon unprepared", "ham": "pork cured ham boneless extra lean and regular unheated",
    "pork chops": "pork loin center loin chops boneless separable lean and fat raw",
    "pork tenderloin": "pork loin tenderloin separable lean only raw", "sausage": "sausage pork raw",
    "italian sausage": "sausage italian pork raw", "beef stew meat": "beef chuck for stew separable lean and fat raw",
    "beef roast": "beef chuck arm pot roast separable lean and fat raw", "steak": "beef top sirloin steak separable lean and fat raw",
    "shrimp": "crustaceans shrimp raw", "salmon": "fish salmon atlantic farmed raw", "tuna": "fish tuna light canned in water drained",
    "tilapia": "fish tilapia raw", "cod": "fish cod atlantic raw", "crabmeat": "crustaceans crab blue raw",
    "onion": "onions raw", "onions": "onions raw", "fresh onion": "onions raw", "red onion": "onions raw", "yellow onion": "onions raw",
    "garlic": "garlic raw", "garlic clove": "garlic raw", "garlic cloves": "garlic raw", "fresh garlic": "garlic raw",
    "tomato": "tomatoes red ripe raw", "tomatoes": "tomatoes red ripe raw", "whole tomatoes": "tomatoes red ripe canned whole",
    "diced tomatoes": "tomatoes red ripe canned", "crushed tomatoes": "tomatoes red ripe canned",
    "tomato sauce": "tomato products canned sauce", "tomato paste": "tomato products canned paste",
    "tomato soup": "soup tomato canned condensed", "ketchup": "catsup", "potato": "potatoes flesh and skin raw",
    "potatoes": "potatoes flesh and skin raw", "sweet potato": "sweet potato raw", "sweet potatoes": "sweet potato raw",
    "carrot": "carrots raw", "carrots": "carrots raw", "celery": "celery raw", "mushroom": "mushrooms white raw",
    "mushrooms": "mushrooms white raw", "fresh mushrooms": "mushrooms white raw", "zucchini": "squash summer zucchini raw",
    "broccoli": "broccoli raw", "spinach": "spinach raw", "fresh spinach": "spinach raw", "cabbage": "cabbage raw",
    "lettuce": "lettuce iceberg raw", "cucumber": "cucumber with peel raw", "avocado": "avocados raw",
    "corn": "corn sweet yellow raw", "frozen corn": "corn sweet yellow frozen kernels", "frozen corn kernels": "corn sweet yellow frozen kernels",
    "peas": "peas green raw", "frozen peas": "peas green frozen", "green beans": "beans snap green raw",
    "black beans": "beans black mature seeds canned", "kidney beans": "beans kidney red mature seeds canned",
    "pinto beans": "beans pinto mature seeds canned", "white beans": "beans white mature seeds canned",
    "lentils": "lentils raw", "red lentils": "lentils raw", "lemon": "lemons raw", "lemons": "lemons raw",
    "lemon juice": "lemon juice raw", "lemon wedge": "lemons raw", "lime": "limes raw", "limes": "limes raw",
    "lime juice": "lime juice raw", "orange juice": "orange juice raw", "apple": "apples raw", "apples": "apples raw",
    "banana": "bananas raw", "bananas": "bananas raw", "raisins": "raisins seedless", "walnuts": "nuts walnuts english",
    "pecans": "nuts pecans", "almonds": "nuts almonds", "peanuts": "peanuts all types raw",
    "peanut butter": "peanut butter smooth style", "creamy peanut butter": "peanut butter smooth style",
    "honey": "honey", "maple syrup": "syrups maple", "molasses": "molasses", "corn syrup": "syrups corn light",
    "chocolate chips": "chocolate dark 45-59% cacao", "semisweet chocolate chips": "chocolate dark 45-59% cacao",
    "cocoa": "cocoa dry powder unsweetened", "cocoa powder": "cocoa dry powder unsweetened",
    "rice": "rice white long-grain regular raw", "white rice": "rice white long-grain regular raw",
    "brown rice": "rice brown long-grain raw", "oats": "oats",
    "rolled oats": "oats", "quick oats": "cereals oats regular and quick not fortified dry",
    "spaghetti": "pasta dry unenriched", "linguine": "pasta dry unenriched", "pasta": "pasta dry unenriched",
    "egg noodles": "noodles egg dry unenriched", "macaroni": "pasta dry unenriched", "bread": "bread white commercially prepared",
    "breadcrumbs": "bread crumbs dry grated plain", "bread crumbs": "bread crumbs dry grated plain",
    "tortillas": "tortillas ready-to-bake or -fry flour", "flour tortillas": "tortillas ready-to-bake or -fry flour",
    "corn tortillas": "tortillas ready-to-bake or -fry corn", "chicken broth": "soup chicken broth canned ready-to-serve",
    "chicken stock": "soup chicken broth canned ready-to-serve", "beef broth": "soup beef broth canned ready-to-serve",
    "vegetable broth": "soup vegetable broth ready to serve", "soy sauce": "soy sauce made from soy and wheat shoyu",
    "worcestershire sauce": "sauce worcestershire", "hot sauce": "sauce hot chile sriracha",
    "tabasco sauce": "sauce ready-to-serve pepper tabasco", "mayonnaise": "salad dressing mayonnaise regular",
    "mustard": "mustard prepared yellow", "dijon mustard": "mustard prepared yellow", "vinegar": "vinegar distilled",
    "white vinegar": "vinegar distilled", "apple cider vinegar": "vinegar cider", "balsamic vinegar": "vinegar balsamic",
    "red wine vinegar": "vinegar red wine", "rice wine": "alcoholic beverage wine table white", "white wine": "alcoholic beverage wine table white",
    "red wine": "alcoholic beverage wine table red", "water": "water bottled generic", "tofu": "tofu firm",
    "extra firm tofu": "tofu firm", "firm tofu": "tofu firm", "coconut milk": "nuts coconut milk canned",
    "wasabi": "wasabi root raw", "pumpkin": "pumpkin canned", "pumpkin pie filling": "pumpkin canned",
    "vanilla yogurt": "yogurt vanilla low fat", "vanilla instant pudding mix": "puddings vanilla dry mix instant",
    "cheddar": "cheese cheddar", "pimentos": "pimento canned", "diced pimentos": "pimento canned",
    "green chilies": "peppers hot chili green canned", "green chiles": "peppers hot chili green canned",
    "tzatziki": "yogurt greek plain whole milk", "salsa": "sauce salsa ready-to-serve",
    "artichoke hearts": "artichokes globe or french frozen", "dill pickle": "pickles cucumber dill or kosher dill",
    "dill pickles": "pickles cucumber dill or kosher dill", "parmigiano-reggiano cheese": "cheese parmesan hard",
    "parmesan": "cheese parmesan grated", "salmon fillets": "fish salmon atlantic farmed raw", "salmon fillet": "fish salmon atlantic farmed raw",
    "frozen blueberries": "blueberries frozen unsweetened", "blueberries": "blueberries raw", "strawberries": "strawberries raw",
    "frozen strawberries": "strawberries frozen unsweetened", "mustard powder": "spices mustard seed ground",
    "chinese wine": "alcoholic beverage wine table white", "rice wine": "alcoholic beverage wine table white",
    "sherry wine": "alcoholic beverage wine table white", "dry sherry": "alcoholic beverage wine table white",
    "baking mix": "biscuits plain or buttermilk dry mix", "bisquick": "biscuits plain or buttermilk dry mix",
    "bisquick baking mix": "biscuits plain or buttermilk dry mix", "boursin cheese": "cheese cream",
    "cooked brown rice": "rice brown long-grain cooked", "cooked rice": "rice white long-grain regular cooked",
    "cooked white rice": "rice white long-grain regular cooked", "brown rice": "rice brown long-grain raw",
    "corn tortilla chips": "tortilla chips yellow plain salted", "cheese slice": "cheese pasteurized process american",
    "chicken bouillon cubes": "soup chicken broth or bouillon dry", "chicken bouillon cube": "soup chicken broth or bouillon dry",
    "chicken bouillon": "soup chicken broth or bouillon dry", "chicken flavor instant bouillon": "soup chicken broth or bouillon dry",
    "beef bouillon cube": "soup beef broth or bouillon powder dry", "beef bouillon cubes": "soup beef broth or bouillon powder dry",
    "stuffing mix": "stuffing bread dry mix", "chicken stove top stuffing mix": "stuffing bread dry mix",
    "pepperidge farm herb stuffing": "stuffing bread dry mix", "chicken pieces": "chicken broilers or fryers meat only raw",
    "skinless chicken piece": "chicken broilers or fryers breast meat only raw", "pumpkin puree": "pumpkin canned",
    "canned pumpkin puree": "pumpkin canned", "canned pumpkin": "pumpkin canned", "lemon pepper seasoning": "spices pepper black",
    "cajun seasoning mix": "spices chili powder", "cajun seasoning": "spices chili powder", "taco seasoning mix": "seasoning mix dry taco original",
    "bulk taco seasoning mix": "seasoning mix dry taco original", "scallion": "onions spring", "chilies": "peppers hot chili green raw",
    "chili": "peppers hot chili green raw", "chipotle chile": "peppers hot chili red raw", "chipotle chiles": "peppers hot chili red raw",
    "anaheim chilies": "peppers hot chili green raw", "jalapeno chile": "peppers jalapeno raw", "green chilies": "peppers hot chili green canned",
    "fettuccine": "pasta dry unenriched", "penne": "pasta dry unenriched", "lasagna noodles": "pasta dry unenriched",
    "cellophane noodle": "noodles chinese cellophane or long rice mung beans dehydrated", "clove": "spices cloves ground",
    "quick-cooking grits": "cereals corn grits white regular and quick dry", "grits": "cereals corn grits white regular and quick dry",
    "kalamata olive": "olives ripe canned", "kalamata olives": "olives ripe canned", "green olives": "olives green",
    "black olives": "olives ripe canned", "garam masala": "spices curry powder", "miracle whip": "salad dressing mayonnaise light",
    "miniature bagels": "bagels plain", "bagels": "bagels plain", "pancetta": "pork cured bacon unprepared",
    "creme fraiche": "cream sour cultured", "navy beans": "beans navy mature seeds canned", "cumin powder": "spices cumin seed",
    "soya sauce": "soy sauce made from soy and wheat shoyu", "saffron thread": "spices saffron", "saffron": "spices saffron",
    "dried rubbed sage": "spices sage ground", "sage": "spices sage ground", "rotel tomatoes & chilies": "tomatoes red ripe canned with green chilies",
    "chili beans": "beans kidney red mature seeds canned", "lemon zest": "lemon peel raw", "orange zest": "orange peel raw",
    "instant coffee granules": "beverages coffee instant regular powder", "ground flax seeds": "seeds flaxseed",
    "asparagus": "asparagus raw", "asparagus spear": "asparagus raw", "cinnamon stick": "spices cinnamon ground",
    "gingerroot": "ginger root raw", "pineapple chunks": "pineapple raw all varieties", "pineapple tidbits": "pineapple raw all varieties",
    "canned pineapple": "pineapple canned juice pack", "splenda sugar substitute": "sweeteners sugar substitute granulated",
    "chives": "chives raw", "tortilla chips": "tortilla chips yellow plain salted",
    "old fashioned oats": "oats", "robin hood oats": "oats", "old mill oats": "oats", "oatmeal": "oats",
    "cooked ham": "pork cured ham boneless extra lean and regular roasted", "deli ham": "pork cured ham boneless extra lean and regular unheated",
    "bean sprouts": "mung beans mature seeds sprouted raw", "cannellini beans": "beans white mature seeds canned",
    "lemon slices": "lemons raw", "lemon rind": "lemon peel raw", "orange rind": "orange peel raw",
    "homemade fresh bacon bits": "pork cured bacon cooked baked", "bacon bits": "pork cured bacon cooked baked",
    "dill pickle slices": "pickles cucumber dill or kosher dill", "liquid smoke": "sauce worcestershire",
    "matzo meal": "crackers matzo plain", "broccoli florets": "broccoli raw", "celery ribs": "celery raw", "celery rib": "celery raw",
    "chickpeas": "chickpeas garbanzo beans mature seeds canned",
    "graham cracker": "crackers graham plain or honey", "graham crackers": "crackers graham plain or honey",
    "graham cracker crumbs": "crackers graham plain or honey", "stewed tomatoes": "tomatoes red ripe canned stewed",
    "chicken tenderloins": "chicken broilers or fryers breast meat only raw", "chicken tenders": "chicken broilers or fryers breast meat only raw",
    "of fresh mint": "spearmint fresh", "fresh mint": "spearmint fresh", "mint": "spearmint fresh",
    "london broil beef": "beef round top round steak separable lean and fat raw",
    "dried ancho chile powder": "peppers ancho dried", "ancho chile powder": "peppers ancho dried",
    # names used by the recommender demo seed
    "chicken breast, cooked": "chicken broilers or fryers breast meat only cooked roasted",
    "salmon, cooked": "fish salmon atlantic farmed cooked dry heat", "broccoli, cooked": "broccoli cooked boiled drained without salt",
    "egg, whole, cooked": "egg whole cooked hard-boiled", "greek yogurt, plain": "yogurt greek plain whole milk",
    "oats, rolled, dry": "oats", "sweet potato, baked": "sweet potato cooked baked in skin flesh without salt",
    "chickpeas, cooked": "chickpeas garbanzo beans mature seeds cooked boiled without salt", "quinoa, cooked": "quinoa cooked",
    "tofu, firm": "tofu firm prepared with calcium sulfate and magnesium chloride nigari", "milk, whole": "milk whole 3.25% milkfat with added vitamin d",
    "rice, white, long-grain, cooked": "rice white long-grain regular enriched cooked", "lentils, cooked": "lentils mature seeds cooked boiled without salt",
    "lemon juice, raw": "lemon juice raw", "garlic, raw": "garlic raw", "spinach, raw": "spinach raw",
}

DROP_WORDS = {"fresh", "chopped", "diced", "minced", "sliced", "large", "small", "medium", "cold", "warm",
              "hot", "boiling", "uncooked", "packed", "finely", "coarsely", "ripe", "of", "and",
              "or", "the", "a", "to", "taste", "optional", "divided", "for", "frying", "melted", "softened",
              "grated", "shredded", "crushed", "ground", "prepared", "fresh-ground", "freshly", "thinly"}
# Words that change what the food is. An entry gets marked down for each one
# it has that the ingredient didn't mention.
SHIFTERS = {"oil", "juice", "peel", "zest", "powder", "flour", "chips", "sauce", "soup", "seeds", "seed",
            "extract", "syrup", "relish", "pie", "pastries", "mix", "flavor", "dry", "dried", "dehydrated",
            "frozen", "canned", "cooked", "roasted", "fried", "baby", "meatless", "substitute", "imitation",
            "bran", "germ", "gravy", "toppings", "candies", "cookies", "crackers", "cereals", "beverages",
            "fat", "cream", "milk", "cheese", "butter", "spread", "dip", "jam", "jelly", "vinegar", "wine"}
AVOID = ["babyfood", "baby food", "fast food", "fast foods", "restaurant", "infant", "formula",
         "school lunch", "dehydrated", "freeze-dried", "kellogg", "general mills", "quaker", "post ",
         "mcdonald", "burger king", "taco bell", "wendy", "kfc", "pizza hut", "domino", "campbell",
         "kraft", "nabisco", "keebler", "pillsbury", "betty crocker", "mission", "martha white",
         "george weston", "nestle", "hormel", "oscar mayer", "smart soup", "healthy request"]


def norm(s):
    s = re.sub(r"[^a-z0-9% ]", " ", str(s).lower().replace("-", " "))
    return " ".join(w for w in s.split() if w not in DROP_WORDS)


def singular(w):
    if w.endswith("ies") and len(w) > 4: return w[:-3] + "y"
    if w.endswith("oes"): return w[:-2]
    if w.endswith("es") and w[:-2].endswith(("sh", "ch", "ss", "x")): return w[:-2]
    if w.endswith("s") and not w.endswith("ss") and len(w) > 3: return w[:-1]
    return w


def query_for(name):
    key = str(name).lower().strip()
    key = re.sub(r"\s+", " ", key)
    if key in ALIASES: return norm(ALIASES[key]), True
    n = norm(name)
    if n in ALIASES: return norm(ALIASES[n]), True
    if "pudding" in n: return norm("puddings vanilla dry mix instant"), True
    # try the last two / last one words (head noun) against aliases
    words = n.split()
    for k in range(min(3, len(words)), 0, -1):
        tail = " ".join(words[-k:])
        if tail in ALIASES: return norm(ALIASES[tail]), True
        tail_s = " ".join(singular(w) for w in words[-k:])
        if tail_s in ALIASES: return norm(ALIASES[tail_s]), True
    return " ".join(singular(w) for w in words), False


def load_sr(folder):
    food = pd.read_csv(os.path.join(folder, "food.csv"), dtype=str)
    food = food[food.data_type == "sr_legacy_food"][["fdc_id", "description", "food_category_id"]]
    cat = pd.read_csv(os.path.join(folder, "food_category.csv"), dtype=str).set_index("id")["description"]
    food["category"] = food.food_category_id.map(cat)
    nut = pd.read_csv(os.path.join(folder, "nutrient.csv"), dtype=str)
    nut["nutrient_nbr"] = nut.nutrient_nbr.str.replace(r"\.0$", "", regex=True)
    wanted = {v: k for k, v in NUTRIENTS.items()}
    nut = nut[nut.nutrient_nbr.isin(wanted)]
    nut_id_to_ours = dict(zip(nut.id, nut.nutrient_nbr.map(wanted)))
    nut_unit = dict(zip(nut.nutrient_nbr.map(wanted), nut.unit_name.map(UNITS)))
    fn = pd.read_csv(os.path.join(folder, "food_nutrient.csv"), dtype=str, usecols=["fdc_id", "nutrient_id", "amount"])
    fn = fn[fn.nutrient_id.isin(nut_id_to_ours)]
    fn["nutrient"] = fn.nutrient_id.map(nut_id_to_ours)
    fn["amount"] = fn.amount.astype(float)
    nutrition = defaultdict(dict)
    for r in fn.itertuples(index=False):
        nutrition[r.fdc_id][r.nutrient] = r.amount
    # typical serving: first portion row with a gram weight
    fp = pd.read_csv(os.path.join(folder, "food_portion.csv"), dtype=str, usecols=["fdc_id", "seq_num", "gram_weight"])
    fp["seq_num"] = fp.seq_num.astype(float)
    fp = fp.sort_values(["fdc_id", "seq_num"]).drop_duplicates("fdc_id")
    serving = dict(zip(fp.fdc_id, fp.gram_weight.astype(float)))
    return food, nutrition, nut_unit, serving


def match_all(names, food, min_score):
    descs = [norm(d) for d in food.description]
    desc_words = [set(singular(w) for w in d.split()) for d in descs]
    fdc = list(food.fdc_id)
    desc_by_i = list(food.description)
    results = []
    for name in names:
        q, aliased = query_for(name)
        qwords = set(singular(w) for w in q.split())
        cands = process.extract(q, descs, scorer=fuzz.token_set_ratio, limit=40)
        best = None
        for _, ratio, i in cands:
            d = desc_by_i[i].lower()
            dw = desc_words[i]
            coverage = len(qwords & dw) / max(len(qwords), 1)
            s = 0.4 * ratio + 60 * coverage
            if any(a in d for a in AVOID): s -= 40
            if re.search(r"\b[A-Z][A-Z'&]{2,}\b", desc_by_i[i]): s -= 40   # USDA writes brands in capitals
            s -= 12 * len((dw & SHIFTERS) - qwords)          # category shift
            if "raw" in dw and "cooked" not in qwords: s += 4
            if "cooked" in qwords and "cooked" in dw: s += 6
            if "with salt" in d and "salt" not in qwords: s -= 6
            s -= min(len(d) / 40, 6)                        # prefer the generic entry
            head = next(iter(q.split()), "")
            if head and descs[i].split()[:1] == [head]: s += 6
            if best is None or s > best[0]: best = (s, i)
        s, i = best
        results.append(dict(name=name, query=q, aliased=aliased, fdc_id=fdc[i],
                            description=desc_by_i[i], score=round(s), ok=s >= min_score))
    return results


def q(v):
    return "NULL" if v is None else "'" + str(v).replace("'", "''") + "'"


def emit(results, food, nutrition, nut_unit, serving, out):
    w = out.write
    cat_by_fdc = dict(zip(food.fdc_id, food.category))
    w("-- Generated by scripts/match_usda.py. Safe to run more than once.\nBEGIN;\n\n")
    for r in results:
        if not r["ok"]: continue
        g = serving.get(r["fdc_id"])
        w(f"UPDATE ingredients SET data_source = 'USDA', "
          f"food_category = {q(cat_by_fdc.get(r['fdc_id'], 'Uncategorized'))}, "
          f"typical_serving_g = coalesce(typical_serving_g, {g if g else 'NULL'}), "
          f"usda_fdc_id = CASE WHEN EXISTS (SELECT 1 FROM ingredients x WHERE x.usda_fdc_id = {r['fdc_id']} "
          f"AND x.ingredient_id <> ingredients.ingredient_id) THEN usda_fdc_id ELSE {r['fdc_id']} END "
          f"WHERE lower(btrim(ingredient_name)) = {q(r['name'].lower().strip())};\n")
        for nid, amount in sorted(nutrition.get(r["fdc_id"], {}).items()):
            w(f"INSERT INTO ingredient_nutrition (ingredient_id, nutrient_id, value_per_100g, unit) "
              f"SELECT ingredient_id, {q(nid)}, {amount}, {q(nut_unit[nid])} FROM ingredients "
              f"WHERE lower(btrim(ingredient_name)) = {q(r['name'].lower().strip())} "
              f"ON CONFLICT (ingredient_id, nutrient_id) DO UPDATE SET value_per_100g = EXCLUDED.value_per_100g, unit = EXCLUDED.unit;\n")
        w("\n")
    w("COMMIT;\n")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("folder", help="unzipped SR Legacy CSV folder")
    p.add_argument("--names", required=True, help="one ingredient name per line")
    p.add_argument("-o", "--out", default="schema/seed/usda_nutrition.sql")
    p.add_argument("--review", default="schema/seed/usda_matches.csv")
    p.add_argument("--min-score", type=int, default=70)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()

    names = [l.strip() for l in open(a.names, encoding="utf-8") if l.strip()]
    food, nutrition, nut_unit, serving = load_sr(a.folder)
    print(f"{len(food):,} SR Legacy foods, {len(names)} ingredient names")
    results = match_all(names, food, a.min_score)
    ok = sum(r["ok"] for r in results)
    print(f"matched {ok} at score >= {a.min_score}, {len(results) - ok} left for review")
    with open(a.review, "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=["ok", "score", "name", "fdc_id", "description", "aliased"])
        wr.writeheader()
        for r in sorted(results, key=lambda r: (r["ok"], r["score"])):
            wr.writerow({k: r[k] for k in wr.fieldnames})
    print(f"-> {a.review}")
    if a.dry_run:
        for r in sorted(results, key=lambda r: r["score"])[:25]:
            print(f"  {r['score']:3} {'ok ' if r['ok'] else 'NO '} {r['name'][:32]:32} -> {r['description'][:60]}")
        return
    with open(a.out, "w", encoding="utf-8") as f:
        emit(results, food, nutrition, nut_unit, serving, f)
    print(f"-> {a.out}")


if __name__ == "__main__":
    main()
