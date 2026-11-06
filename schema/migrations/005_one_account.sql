-- 005_one_account.sql
-- One account system, and one place where a person's facts are written.
--
-- Before this there were two. Signing up wrote auth.users; finishing the
-- onboarding questionnaire wrote households / household_members /
-- member_conditions; and user_profile was written by nothing at all - its only
-- row came from schema/seed/user_example.sql by hand. So the data team's
-- POST /api/login could only ever sign in that one seeded row, and the rules
-- engine's ?user_id= could only ever describe it.
--
-- The two also store the same facts in different vocabularies, and the
-- translation is not reversible:
--
--   sex        household_members F | M
--              user_profile      female | male | other | prefer_not_to_say
--   activity   household_members sedentary | lightly_active | moderate | very_active | athlete
--              user_profile      sedentary | light | moderate | active | very_active
--   goal       household_members maintenance | weight_loss | muscle_gain | wellness
--              user_profile      maintain_weight | lose_weight | gain_weight
--
-- 'wellness' and 'athlete' have no counterpart. Writing both tables from the
-- application would mean maintaining that mapping in code and silently
-- rounding those two values to something a person did not choose - values that
-- then feed a nutrient target calculation.
--
-- So: household_members stays the only table anything writes, and user_profile
-- is kept in step by the database. The translation lives in one function, the
-- two unmappable values become NULL rather than a guess, and nothing in
-- scripts/api.py, scripts/auth.py or the ?user_id= parameter has to change.
--
-- user_profile.user_id is set to member_id, so the two systems share one
-- identifier and no mapping table is needed anywhere.
--
-- What is deliberately left alone: the Maya row from the seed. It has no
-- member_id and no account, and the data team's demo and tests depend on it.
-- The sync only ever touches rows whose user_id is a member_id.

BEGIN;

-- ---------------------------------------------------------------- the link
-- Which account a profile belongs to. NULL for the seeded demo row, and for
-- household members who are not the account holder - a child or a partner has
-- a profile and no login, which is the normal case rather than an error.
ALTER TABLE user_profile
    ADD COLUMN IF NOT EXISTS auth_user_id UUID;

ALTER TABLE user_profile
    DROP CONSTRAINT IF EXISTS fk_user_profile_auth;
ALTER TABLE user_profile
    ADD CONSTRAINT fk_user_profile_auth
    FOREIGN KEY (auth_user_id) REFERENCES auth.users (id) ON DELETE SET NULL;

-- One profile per account. Household members without a login are exempt,
-- which is what a partial index gives and a plain UNIQUE would not.
CREATE UNIQUE INDEX IF NOT EXISTS uq_user_profile_auth_user
    ON user_profile (auth_user_id)
    WHERE auth_user_id IS NOT NULL;

-- The onboarding questionnaire lets a person skip their age and sex. Both
-- columns were NOT NULL here, so the sync below would fail and take the
-- questionnaire down with it. The data team's own response model already
-- types them as optional (UserProfileResponse in scripts/api.py), so this
-- matches what the API has always claimed.
ALTER TABLE user_profile ALTER COLUMN age_years DROP NOT NULL;
ALTER TABLE user_profile ALTER COLUMN sex       DROP NOT NULL;

COMMENT ON COLUMN user_profile.auth_user_id IS
    'The Supabase account this profile belongs to, or NULL for a household member with no login.';

-- -------------------------------------------------------- the one translation
CREATE OR REPLACE FUNCTION public.fn_user_profile_sync(p_member_id UUID)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_catalog
AS $$
DECLARE
    m          household_members;
    v_owner    UUID;
    v_allergy  TEXT[];
BEGIN
    SELECT * INTO m FROM household_members WHERE member_id = p_member_id;
    IF NOT FOUND OR m.deleted_at IS NOT NULL THEN
        RETURN;
    END IF;

    -- The account holder is whoever created the household. Other members of
    -- it get a profile with no account, which is correct: they do not log in.
    SELECT h.created_by_user_id INTO v_owner
      FROM households h
     WHERE h.household_id = m.household_id
       AND h.deleted_at IS NULL;

    -- Allergies are one row each in member_conditions and one array here.
    SELECT array_agg(DISTINCT btrim(mc.value_text))
      INTO v_allergy
      FROM member_conditions mc
     WHERE mc.member_id = m.member_id
       AND mc.condition_type = 'allergy'
       AND nullif(btrim(mc.value_text), '') IS NOT NULL;

    INSERT INTO user_profile AS up (
        user_id, auth_user_id, name, age_years, sex, height_cm, weight_kg,
        activity_level, goal, diet_type, allergies, preferences, updated_at
    )
    VALUES (
        m.member_id,
        -- Only the first member of a household is the account holder. Matching
        -- on profile_email would be wrong: an invited member's email is not
        -- the account that created the household.
        CASE WHEN m.member_id = (
                 SELECT member_id FROM household_members
                  WHERE household_id = m.household_id AND deleted_at IS NULL
                  ORDER BY created_at, member_id LIMIT 1)
             THEN v_owner END,
        m.member_name,
        m.age,
        CASE m.sex_at_birth WHEN 'F' THEN 'female' WHEN 'M' THEN 'male' END,
        m.height_cm,
        m.weight_kg,
        -- 'athlete' maps to the highest value user_profile has; 'lightly_active'
        -- to its 'light'. The rest are spelled the same on both sides.
        CASE m.activity_level
            WHEN 'lightly_active' THEN 'light'
            WHEN 'athlete'        THEN 'very_active'
            ELSE m.activity_level
        END,
        -- 'wellness' becomes NULL on purpose. user_profile has no value for
        -- "improve health", and picking the nearest one would put a goal the
        -- person did not choose in front of a target calculation.
        CASE m.goal
            WHEN 'maintenance' THEN 'maintain_weight'
            WHEN 'weight_loss' THEN 'lose_weight'
            WHEN 'muscle_gain' THEN 'gain_weight'
        END,
        m.lifestyle_dietary[1],
        v_allergy,
        m.food_preference_csv,
        now()
    )
    ON CONFLICT (user_id) DO UPDATE SET
        auth_user_id   = coalesce(excluded.auth_user_id, up.auth_user_id),
        name           = excluded.name,
        age_years      = excluded.age_years,
        sex            = excluded.sex,
        height_cm      = excluded.height_cm,
        weight_kg      = excluded.weight_kg,
        activity_level = excluded.activity_level,
        goal           = excluded.goal,
        diet_type      = excluded.diet_type,
        allergies      = excluded.allergies,
        preferences    = excluded.preferences,
        updated_at     = now();
END;
$$;

COMMENT ON FUNCTION public.fn_user_profile_sync(UUID) IS
    'Mirrors one household_members row into user_profile, translating the two vocabularies. The only place that mapping exists.';

-- ------------------------------------------------------------- the triggers
CREATE OR REPLACE FUNCTION public.trg_member_to_profile()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_catalog
AS $$
BEGIN
    PERFORM public.fn_user_profile_sync(NEW.member_id);
    RETURN NULL;
END;
$$;

-- member_conditions carries the allergies, and saveHousehold() inserts the
-- members first and the conditions after - so without this second trigger
-- every profile would be written before its allergies existed and keep an
-- empty array. DELETE matters too: removing an allergy has to remove it here.
CREATE OR REPLACE FUNCTION public.trg_condition_to_profile()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_catalog
AS $$
BEGIN
    PERFORM public.fn_user_profile_sync(
        CASE WHEN TG_OP = 'DELETE' THEN OLD.member_id ELSE NEW.member_id END);
    RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS t_member_to_profile ON household_members;
CREATE TRIGGER t_member_to_profile
    AFTER INSERT OR UPDATE ON household_members
    FOR EACH ROW EXECUTE FUNCTION public.trg_member_to_profile();

DROP TRIGGER IF EXISTS t_condition_to_profile ON member_conditions;
CREATE TRIGGER t_condition_to_profile
    AFTER INSERT OR UPDATE OR DELETE ON member_conditions
    FOR EACH ROW EXECUTE FUNCTION public.trg_condition_to_profile();

-- Backfill whatever already exists. Empty on this database today, but a
-- migration that only works on an empty table is a migration that fails the
-- first time it meets real data.
DO $$
DECLARE r RECORD;
BEGIN
    FOR r IN SELECT member_id FROM household_members WHERE deleted_at IS NULL LOOP
        PERFORM public.fn_user_profile_sync(r.member_id);
    END LOOP;
END;
$$;

COMMIT;

-- ---------------------------------------------------------------------------
-- Removal, added after testing found it missing.
--
-- The triggers above fire on INSERT and UPDATE, so a member who is deleted -
-- or soft-deleted, which is what the app does - left their profile behind.
-- That is not a tidiness problem: the profile row holds age, sex, height,
-- weight and allergies, and ?user_id=<their old member_id> would still return
-- all of it after they had been removed from the household.
--
-- Deleting the profile also removes their nutrient targets, through the
-- ON DELETE CASCADE already on user_nutrient_targets, which is what should
-- happen to targets computed for someone no longer there.
--
-- The seeded demo row is unaffected: no member_id equals it.
-- ---------------------------------------------------------------------------

BEGIN;

CREATE OR REPLACE FUNCTION public.fn_user_profile_forget(p_member_id UUID)
RETURNS void
LANGUAGE sql
SECURITY DEFINER
SET search_path = public, pg_catalog
AS $$
    DELETE FROM user_profile WHERE user_id = p_member_id;
$$;

COMMENT ON FUNCTION public.fn_user_profile_forget(UUID) IS
    'Removes the mirrored profile of a deleted or soft-deleted household member, and their targets with it.';

-- A soft delete arrives as an UPDATE, so the sync function has to notice it
-- rather than returning early and leaving the old row in place.
CREATE OR REPLACE FUNCTION public.trg_member_to_profile()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_catalog
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        PERFORM public.fn_user_profile_forget(OLD.member_id);
    ELSIF NEW.deleted_at IS NOT NULL THEN
        PERFORM public.fn_user_profile_forget(NEW.member_id);
    ELSE
        PERFORM public.fn_user_profile_sync(NEW.member_id);
    END IF;
    RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS t_member_to_profile ON household_members;
CREATE TRIGGER t_member_to_profile
    AFTER INSERT OR UPDATE OR DELETE ON household_members
    FOR EACH ROW EXECUTE FUNCTION public.trg_member_to_profile();

-- Removing an allergy must not resurrect the profile of a member who is
-- already gone. fn_user_profile_sync returns early when the member row is
-- missing or soft-deleted, so the guard belongs there - but member_conditions
-- rows are deleted by the cascade from household_members, and the order of
-- the two is not something to rely on. Checking here is explicit.
CREATE OR REPLACE FUNCTION public.trg_condition_to_profile()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_catalog
AS $$
DECLARE
    v_member UUID := CASE WHEN TG_OP = 'DELETE' THEN OLD.member_id ELSE NEW.member_id END;
BEGIN
    IF EXISTS (SELECT 1 FROM household_members
                WHERE member_id = v_member AND deleted_at IS NULL) THEN
        PERFORM public.fn_user_profile_sync(v_member);
    END IF;
    RETURN NULL;
END;
$$;

COMMIT;
