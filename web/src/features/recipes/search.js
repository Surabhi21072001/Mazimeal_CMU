// How both recipe pickers search: on words, not on the whole string, so
// "bean rice" finds "Gallo Pinto (Costa Rican Rice and Beans)" whichever order
// the words are typed in. Name, cuisine and meal are all searchable, because
// "mediterranean" is as likely a thing to type as a dish name.
export function matches(item, query) {
  if (!query) return true;
  const haystack = `${item.name} ${item.cuisine || ""} ${item.meal || ""}`.toLowerCase();
  return query
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .every((word) => haystack.includes(word));
}
