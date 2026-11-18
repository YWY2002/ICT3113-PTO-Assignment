# Golden-set split (Assignment 2, Step 1)

Committed before any Assignment 2 rule design or measurement.

## Rule

Sort the 150 golden-set tickets in `Golden_Test_Set/Final Golden Test Set.xlsx` by dataset row number (the `row` column, ascending). Counting from 1 in that sorted order, tickets in **odd positions** (1st, 3rd, ..., 149th) form the **tuning set** and tickets in **even positions** (2nd, 4th, ..., 150th) form the **test set**.

This implements the brief's instruction "Sort your golden-set tickets by row number. Odd rows are your tuning set. Even rows are your test set." with "odd rows" read as odd positions in the sorted list. The instruction to sort first only changes the result under this reading; with odd/even row *numbers*, order would not matter.

- **Tuning set** (`tuning_rows.csv`): used only to design and adjust the cascade escalation rule and to choose its two settings.
- **Test set** (`test_rows.csv`): used for every reported accuracy figure, including the overall and per-category limits derived from the top model.

Regenerate with `python assignment2/split/make_split.py`.

## Tickets per category

| Category | Golden | Tuning | Test |
|---|---:|---:|---:|
| Credit reporting | 38 | 19 | 19 |
| Debt collection | 8 | 4 | 4 |
| Mortgage | 19 | 10 | 9 |
| Credit card | 16 | 6 | 10 |
| Bank account or service | 39 | 18 | 21 |
| Consumer loan | 14 | 10 | 4 |
| Money transfer or service | 16 | 8 | 8 |
| **Total** | **150** | **75** | **75** |

## Row numbers

**Tuning set (75):** 5010, 5025, 5039, 5054, 5059, 5066, 5070, 5076, 5088, 5101, 5120, 5139, 5174, 5198, 5210, 5218, 5235, 5244, 5256, 5261, 5275, 5280, 5289, 5294, 5299, 5312, 5319, 5327, 5346, 5370, 5382, 5425, 5436, 5445, 5493, 5513, 5522, 5528, 5534, 5543, 5549, 5559, 5578, 5584, 5590, 5601, 5617, 5626, 5636, 5652, 5662, 5679, 5692, 5714, 5721, 5740, 5753, 5764, 5800, 5811, 5820, 5823, 5837, 5859, 5867, 5883, 5893, 5901, 5914, 5924, 5938, 5959, 5974, 5985, 5995

**Test set (75):** 5023, 5030, 5044, 5055, 5063, 5067, 5072, 5086, 5096, 5107, 5136, 5168, 5184, 5209, 5215, 5221, 5237, 5247, 5260, 5265, 5277, 5281, 5292, 5296, 5307, 5318, 5321, 5328, 5351, 5371, 5411, 5432, 5439, 5451, 5499, 5521, 5527, 5529, 5542, 5548, 5554, 5570, 5583, 5589, 5599, 5604, 5621, 5635, 5644, 5660, 5678, 5687, 5713, 5716, 5737, 5741, 5761, 5787, 5810, 5816, 5822, 5826, 5849, 5866, 5879, 5892, 5899, 5902, 5917, 5936, 5947, 5973, 5978, 5986, 5998
