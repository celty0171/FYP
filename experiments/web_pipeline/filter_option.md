# Filter / Aggregate / Join — 使用說明 (Usage guide) · 中英雙語

> 網頁在原本的「選表 + 選欄」之外，增加了三個資料加工階段：**Join(跨表帶欄)**、
> **Filter(同表篩選)**、**Aggregate(同表聚合)**。三者都是可選的；全部留空時，行為與
> 加工前完全一致。管線固定順序為 **Join → Filter → Aggregate → Step 1/2/3**。
>
> On top of the original "pick a table + pick columns", the web app adds three optional data-preparation
> stages: **Join** (bring in a column from another table), **Filter** (subset rows of the same table),
> and **Aggregate** (summarise rows of the same table). All are optional; leaving them empty reproduces
> the original behaviour. The fixed pipeline order is **Join → Filter → Aggregate → Step 1/2/3**.

---

## 總覽 / At a glance

| 階段 Stage | 作用 What it does | 何時用 When to use |
|---|---|---|
| **Join** | 沿外鍵關係，把**別的表**的某欄附加到當前表的每一列 / Attach a column from a **related table** to each row via the foreign-key graph | 想用的欄位不在當前表(例：`country_population` 想按 `continent` 看)/ The column you want isn't in the base table (e.g. `country_population` by `continent`) |
| **Filter** | 只保留**符合條件**的列(WHERE)/ Keep only the rows that **match a condition** | 只想看某時間範圍 / 某類別(例：`year 1990–2020`、`continent = Europe`)/ Restrict to a time range or category |
| **Aggregate** | 把多列**匯總成每組一列**(group-by + 統計)/ Collapse many rows into **one row per group** (group-by + measures) | 想看總和 / 平均 / 計數，而非原始列(例：各洲人口總和)/ You want sums / averages / counts, not raw rows |

- **不改變 pattern**:Join 只是加一個屬性欄,不會改變 Step 1 判定的 ER pattern。
  Aggregate 會產生一張「衍生表」,通常被判為 `basic_entity`。
  **Pattern-safe**: Join only adds an attribute (it never changes the ER pattern Step 1 identifies).
  Aggregate produces a *derived table*, usually classified as `basic_entity`.
- **加工後圖表自動更新**:資料變了,Step 2 會在新資料上重新推薦圖表。
  **Recommendations adapt**: because the data changes, Step 2 re-recommends charts on the new data.

---

## 基本流程 / Basic flow

1. **選表 + 勾欄位**(左上「1. Selection」)。這一步必須;其餘三個都是可選加工。
   **Pick a table + tick columns** (top-left "1. Selection"). Required; the other three are optional.
2. 設定 Join / Filter / Aggregate(見下)。/ Configure Join / Filter / Aggregate (below).
3. 按 **「Run pipeline」**。右側顯示 pattern、推薦圖表的**膠囊(pill)**;點任一膠囊即渲染該圖。
   Click **"Run pipeline"**. The right side shows the pattern and recommended-chart **pills**; click a pill to render it.
4. 改了任何加工,要**重新按 Run**。/ After changing any stage, **click Run again**.

---

## Join —「Related columns (join)」

**作用 / Purpose.** 當你要的欄位不在當前表時,沿外鍵路徑把它帶進來,之後就能像原生欄位一樣被
Filter 與 Aggregate 使用。
When the column you want lives in another table, pull it in along the FK path; afterwards it can be
filtered and grouped just like a native column.

**操作 / Steps.**
1. 下拉「Related columns (join)」會列出從當前表**可達的外表欄位**,標註 `N-hop`;若可能使列數翻倍,標
   `⚠ may duplicate`。/ The dropdown lists **reachable foreign columns**, tagged `N-hop`; a
   `⚠ may duplicate` marks a join that can multiply rows.
2. 選一個(例:`encompasses.continent`),按 **「+ add related column」**,它會變成一個標籤(chip)。/
   Pick one (e.g. `encompasses.continent`) and click **"+ add related column"**; it becomes a chip.
3. 若該欄標了 `⚠`(多對多,如一國跨兩洲),chip 上有 `first / explode` 切換:
   Multiplying joins show a `first / explode` toggle:
   - **`first`**(預設)每列只取一個匹配,**列數不變**,較安全。/ keep one match, **row count unchanged** (safe default).
   - **`explode`** 每個匹配展開成一列,**列數會變多**,適合「只看某洲」之類的過濾。/ one row per match,
     **row count grows** — good for filtering to one category.
4. 加了 Join 後,新欄位會**自動出現**在 Filters 與 Aggregate 的選項裡。/ Once joined, the new column
   **automatically appears** in the Filters and Aggregate options.

> 命名衝突時會自動加前綴,如把 `province.population` 帶到已有 `population` 的表 → `province__population`。
> On a name clash the column is namespaced, e.g. bringing `province.population` into a table that already
> has `population` → `province__population`.

---

## Filter —「2. Filters」

**作用 / Purpose.** 只保留符合條件的列;不改變「一列代表什麼」。
Keep only matching rows; it never changes what a row *means*.

**操作 / Steps.** 面板依欄位型別**自動生成控件**,無需手動設定:
The panel **auto-builds a control per column** from its type:
- **數值 / 時間欄(如 `year`、`population`)** → 兩個輸入框「最小 – 最大」,灰字佔位顯示資料實際範圍;
  填一邊或兩邊即可,留空 = 不限。/ **numeric / temporal** → two "min – max" boxes (placeholder shows the
  real data range); fill either or both; empty = unbounded.
- **類別欄(如 `continent`)** → 勾選清單,預設全勾(= 不篩);取消一些就只保留勾選的。/ **categorical** →
  a checklist, all ticked by default (= no filter); untick some to keep only the ticked values.
- **高基數欄**(太多不同值)→ 不提供控件,顯示提示。/ **high-cardinality** columns show a hint instead of a control.

下方有一行**條件摘要**;「Clear filters」清空。/ A one-line **summary** shows the active conditions;
"Clear filters" resets them.

---

## Aggregate —「3. Aggregate」

**作用 / Purpose.** 把多列匯總成「每組一列」。結果是一張衍生表(group 鍵 = 主鍵,統計量 = 度量),通常
被判為 `basic_entity`,並用**現有的** Step 1→2→3 出圖。
Collapse rows into "one row per group". The result is a derived table (group keys = primary key,
measures = attributes), usually classified as `basic_entity`, visualised through the **existing** pipeline.

**操作 / Steps.**
- **Group by**:勾選分組依據(例:`continent` 或 `year`)。/ tick the grouping key(s) (e.g. `continent` or `year`).
- **Measures**:每行選「函數 + 欄位 + 別名」;函數有 `sum / mean / min / max / count / count_distinct`;
  「+ measure」可加多個。(`count` 不需選欄位。)/ each row is "function + column + alias"; functions are
  `sum / mean / min / max / count / count_distinct`; "+ measure" adds more. (`count` needs no column.)
- **Resample(可選)**:把數值/時間欄分桶,例:`year` bucket `10` as `decade`,分出的 `decade` 會自動加進
  Group by 選項。/ bucket a numeric/temporal column, e.g. `year` bucket `10` as `decade`; the derived
  `decade` is added to the Group-by options.

> 有聚合時,圖表描述的是**組**,不是原始列(面板下方會提示 "chart describes groups, not raw rows")。
> With aggregation on, the chart describes **groups**, not raw rows (the panel notes this).

---

## 串起來:一個完整例子 / A worked example

**目標 / Goal.** 看某個大洲(如 Europe)的人口隨時間變化。/ See population change over time in a continent (e.g. Europe).

**看法 A — 該洲各國的人口趨勢(折線圖) / Per-country trends (line chart).**
1. 選 `country_population`,勾 `country`、`year`、`population`。/ Table `country_population`; tick `country`, `year`, `population`.
2. **Join**:加 `encompasses.continent`(policy = `first`)。/ Join `encompasses.continent` (policy `first`).
3. **Filter**:`continent` 只勾 `Europe`。/ In Filters, tick only `Europe`.
4. **Aggregate**:留空。/ Leave empty.
5. **Run** → `weak_entity` → **line chart**(一國一條線,隨年份變化)。/ → `weak_entity` → **line chart** (one line per country over years).

**看法 B — 該洲的人口總和逐年變化 / Continent total over time.**
- 前 3 步相同;第 4 步 **Aggregate**:Group by `year`,Measure `sum(population)`。/ Same first 3 steps;
  then Aggregate: Group by `year`, Measure `sum(population)`.
- **Run** → `basic_entity` → 逐年人口總和的長條圖。/ → `basic_entity` → a bar chart of yearly totals.

**口訣 / Rule of thumb.** 先決定**資料從哪來**(選表 + Join),再決定**看哪一部分**(Filter),最後決定
**怎麼匯總**(Aggregate),然後 Run 選圖。每個階段留空 = 不加工。
Decide **where the data comes from** (table + Join), then **which part to see** (Filter), then **how to
summarise** (Aggregate), then Run and pick a chart. Any stage left empty = no-op.

---

## 疑難排解 / Troubleshooting

- **改了設定沒反應** → 記得**重新按 Run**;若剛改過 `server.py`,需**重啟 server**(它在啟動時載入程式碼)。
  **No change after editing** → click **Run** again; if `server.py` was edited, **restart the server** (it loads code at startup).
- **圖表一片空白** → 多半是圖表無法載入 D3。server 已將 D3 **內嵌**進圖表 HTML(離線可用);若仍空白,
  按 **Ctrl-Shift-R** 硬刷新,並看瀏覽器 **F12 → Console** 的錯誤。
  **Blank chart** → usually D3 failed to load. The server now **inlines** D3 into each chart's HTML (works
  offline); if still blank, hard-refresh (**Ctrl-Shift-R**) and check **F12 → Console** for errors.
- **"no rows match the current filter"** → 篩選條件過嚴,放寬即可。/ The filter is too strict — relax it.
