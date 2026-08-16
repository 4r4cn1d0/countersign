from col_stats import column_max, column_mean
from export_util import render_row, render_table


assert column_mean(["2", "4"]) == 3.0
assert column_mean(["4", "", "8"]) == 6.0
assert column_mean([]) == 0.0
assert column_mean(["", "  ", ""]) == 0.0
assert column_max(["4", "", "8"]) == 8.0
assert column_max([]) == 0.0
assert render_row(["a", 1]) == "a,1"
assert render_table([["a", 1], ["b", 2]]) == "a,1\nb,2"
print("hidden column-stats validation passed")
