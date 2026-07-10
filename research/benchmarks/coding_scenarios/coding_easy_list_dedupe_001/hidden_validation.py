from counts import count_unique
from dedupe import dedupe


assert dedupe(["b", "a", "b", "a", "c"]) == ["b", "a", "c"]
assert dedupe([]) == []
assert dedupe(["x"]) == ["x"]
assert dedupe(["A", "a", "A"]) == ["A", "a"]
assert count_unique(["a", "b", "a"]) == 2
print("hidden dedupe validation passed")
