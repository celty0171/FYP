# Reducing overlap & clutter in relationship charts (sankey / chord / arc / force)

Research note. Records algorithmic options for the shared clutter problem observed in the
node-link relationship renderers built under `results/viz_codegen_*`.

## The problem

The Step-3 renderers for **sankey**, **chord**, **arc** and **force** all produce visually
cluttered output: heavy overlap of ribbons/links, crossing arcs, and colliding labels. This is
not four separate bugs — all four are **graph (network) visualisations**, and they share one root
difficulty from the graph-drawing literature: *how to place nodes and route links so that
**crossings** and **overlap** are minimised*. Most exact versions of this are NP-hard, so practice
relies on heuristics.

Clutter decomposes into three kinds of overlap:

1. **Node overlap** — nodes drawn on top of each other.
2. **Edge crossing** — links passing through one another.
3. **Label overlap** — text colliding.

The dominant lever for crossings, across all four charts, is **node ordering / seriation**: place
tightly-connected nodes at adjacent positions and crossings drop sharply.

## General framework & cross-cutting algorithms

- **Sugiyama layered framework** (layered graph drawing): assign layers → order within layers to
  reduce crossings → assign coordinates. Sankey is a direct application.
- **Crossing-minimisation heuristics**: **Barycenter** and **Median** — place each node at the
  mean / median position of its neighbours, then sweep iteratively to convergence. Stronger:
  **sifting**. This is the shared workhorse for sankey, arc and chord ordering.
- **Seriation / matrix reordering** — find a good 1-D node order. Methods: **spectral ordering**
  (Fiedler vector of the graph Laplacian), **hierarchical clustering + optimal leaf ordering**,
  and **TSP-style ordering**.
- **Density reduction** — **filtering**, **aggregation**, and **edge bundling**: reduce what must
  be drawn before worrying about layout.

## Per-chart algorithms

### Force-directed graph
Clutter = the "hairball": nodes bunched, edges all crossing.
- **Collision force** — `d3.forceCollide(radius)`: treat nodes as circles, hard-prevent node
  overlap. Cheapest, highest-impact fix.
- **Stronger layout algorithms** — **ForceAtlas2** (Gephi; separates communities),
  **Fruchterman–Reingold**, **Kamada–Kawai** (graph-theoretic distances, fewer crossings),
  multilevel **Yifan Hu / OpenORD** for large graphs. Core idea = **stress majorization**
  (screen distance ≈ shortest-path distance).
- **Overlap removal post-processing** — **VPSC** (Variable Placement with Separation Constraints),
  **PRISM**, scan-line methods (implemented in WebCola).
- **Edge bundling** — **FDEB** (force-directed) and **hierarchical edge bundling** group nearby
  edges into bundles.
- **Filtering / density reduction** — keep only nodes above a degree threshold, or use **k-core
  decomposition** to strip sparse periphery.
- **Label only hubs** — label high-degree nodes only.

### Chord diagram
Clutter = ribbons crossing inside the circle, plus crowded circumference labels.
- **Reorder nodes around the circle** — circular-layout crossing minimisation (NP-hard). Use
  **barycenter / median** heuristics, or **hierarchical clustering + optimal leaf ordering**, so
  strongly-connected entities sit adjacent and ribbons need not span the circle.
- **Gansner & Koren, *Improved Circular Layouts*** — the canonical reference for reducing edge
  crossings and ink in circular layouts.
- **Aggregate small flows** — merge tiny ribbons into an "other", or set a minimum threshold.
- **Visual** — semi-transparent ribbons, larger group padding (gaps), hover-highlight.

### Arc diagram
Nodes on a line; clutter is **almost entirely determined by the linear node order** — good order ≈
no crossings, bad order = large crossing arcs.
- **1-D ordering optimisation** — **spectral (Fiedler) ordering**, **seriation**, or **barycenter**
  iteration. Same problem as chord, on a line instead of a circle.
- **Alternate arcs above/below the baseline** — halves visual density.
- **Scale arc height / opacity by span or weight**.

**Implementation (2026-07-08, `results/viz_codegen_arc/sonnet_arc_v2.py`).** The ordering objective was
tightened from *minimise crossings* to *minimise every arc's span* — both the total span `Σ|i−j|`
(minimum linear arrangement) **and** the maximum span `max|i−j|` (graph bandwidth). The maximum matters
because the canvas height is set by the *tallest* arc, so one long-range **"bridge"** arc balloons the
whole figure into a heavy, mostly-empty slab. Chosen std-lib algorithm: a **spectral (Fiedler) seed per
connected component + barycenter refinement** — order each component by the eigenvector of the
second-smallest Laplacian eigenvalue (minimises `Σ(x_i−x_j)²`, penalising long arcs *super-linearly*,
computed by deterministic power iteration on `cI − L`), then refine by weighted barycenter, keeping the
shortest-total-span pass. Measured on Mondial `borders` (n=169, 326 edges): crossings **16772 → 985**,
longest arc **span 164 → 27** (from spanning 97 % of the axis to ~16 %); `merges_with`: crossings
**1264 → 159**. Two orders were rejected: a plain **degree order** (worst — hubs piled at one end), and a
**min-degree-start RCM** (can leave a single whole-axis bridge arc even when every other arc is short).
Determinism is preserved by seeding the power iteration from a fixed demeaned ramp. Mirrored as general
guidance in `prompts/viz_codegen/chart_arc.md` step 4.

### Sankey diagram
d3-sankey already applies the **Sugiyama framework** internally (layer by FK dependency → order
within layer → assign coordinates). Clutter is usually under-iteration or unturned parameters.
- **Increase within-layer ordering iterations** — `.iterations(n)` runs barycenter/median
  relaxation; more sweeps → fewer crossings.
- **Tune `nodePadding` / `nodeWidth`** — spread nodes within a layer.
- **Within-layer node ordering** — median heuristic against upstream/downstream neighbours.
- **Cycle handling** — reflexive relationships can form cycles that make links wander; break the
  cycle (feedback arc set) before layering.
- **Aggregate small links**.

## Recommended landing order for this project (D3 v7)

Sorted by low-effort / high-impact:

1. **Force** — add `d3.forceCollide()`; add degree / k-core filtering on sparse graphs. Usually
   fixes most of the force clutter alone.
2. **Arc & Chord** — implement one **shared node-ordering module** (barycenter iteration or
   spectral ordering); their ordering problems are isomorphic (line vs circle), so one algorithm
   serves both. This is the root-cause fix for crossings in both.
3. **Sankey** — first tune `.iterations()` and `nodePadding` (near-zero cost); then handle cycles.
4. **Global density reduction** — apply threshold filtering + small-value aggregation across all
   four; any layout is cleaner on a sparser graph.
5. **Interactive fallback** — hover-highlight the relevant nodes/edges and fade the rest
   (focus + context) so local structure stays readable even where crossings remain.

## One-line summary

The clutter in all four charts is one **graph crossing-minimisation** problem in different guises.
The main line of attack is: **node ordering (barycenter / spectral / seriation) + filtering &
aggregation to cut density + post-layout overlap removal (forceCollide / VPSC) + edge bundling**,
with the **Sugiyama framework** and **barycenter/median heuristics** running through all of it.

---

# 減少關係圖重疊與雜亂（sankey / chord / arc / force）— 繁體中文版

研究筆記。記錄針對 `results/viz_codegen_*` 下 node-link 關係圖渲染器所共有的雜亂問題的演算法選項。

## 問題

Step-3 為 **sankey**、**chord**、**arc**、**force** 建的渲染器都產生視覺上雜亂的結果：ribbon/link
大量重疊、弧線互相交叉、標籤互相碰撞。這並非四個獨立的 bug——四者本質上都是**圖（network）的可視化**，
共享圖繪製（graph drawing）領域同一個根本難題：*如何排布節點、走線連結，使得**交叉（crossing）**與
**重疊（overlap）**最少*。此問題的精確版本多為 NP-hard，實務上都靠啟發式演算法。

雜亂可拆成三類重疊：

1. **節點重疊**（node overlap）——節點畫在一起。
2. **連線交叉**（edge crossing）——連結互相穿過。
3. **標籤重疊**（label overlap）——文字擠在一起。

減少交叉的主要槓桿，橫跨四種圖，都是**節點排序 / 序列化（node ordering / seriation）**：把緊密相連
的節點放在相鄰位置，交叉就大幅下降。

## 通用框架與跨圖演算法

- **Sugiyama 分層框架**（layered graph drawing）：分層 → 層內排序以減少交叉 → 坐標分配。Sankey 即其
  直接應用。
- **交叉最小化啟發式**：**Barycenter（重心法）** 與 **Median（中位數法）**——把每個節點放到其鄰居的
  平均／中位位置，反覆掃描迭代至收斂。更強者有 **sifting**。這是 sankey、arc、chord 排序的共用武器。
- **序列化 / Seriation（矩陣重排序）**——為節點找出好的一維順序。方法：**譜排序（spectral，Laplacian
  的 Fiedler 向量）**、**層次聚類 + 最優葉排序（optimal leaf ordering）**、以及 **TSP 式排序**。
- **降密度三板斧**——**過濾（filtering）**、**聚合（aggregation）**、**邊捆綁（edge bundling）**：先減少
  要畫的元素，再談布局。

## 各圖演算法

### 力導向圖（Force-directed）
雜亂 = 「毛球效應」：節點堆疊、邊全交叉。
- **碰撞力（collision force）**——`d3.forceCollide(radius)`：把節點當作有半徑的圓，硬性防止節點重疊。
  成本最低、見效最快。
- **更強的布局演算法**——**ForceAtlas2**（Gephi 用，可分離社群）、**Fruchterman–Reingold**、
  **Kamada–Kawai**（基於圖論距離，交叉更少）、多層次的 **Yifan Hu / OpenORD**（適合大圖）。核心思想是
  **stress majorization（應力優化）**（螢幕距離 ≈ 最短路距離）。
- **布局後去重疊（overlap removal）**——**VPSC**（Variable Placement with Separation Constraints）、
  **PRISM**、scan-line 掃描法（WebCola 有實作）。
- **邊捆綁（edge bundling）**——**FDEB**（力導向）與 **hierarchical edge bundling** 把走向相近的邊捆成束。
- **過濾 / 降密度**——只保留度數超過閾值的節點，或用 **k-core 分解**剝掉稀疏外圍。
- **只標樞紐**——只給高度數節點加標籤。

### 弦圖（Chord）
雜亂 = 圓內 ribbon 互相穿過，以及圓周標籤擁擠。
- **重排圓周節點順序**——圓形布局的交叉最小化（NP-hard）。用 **barycenter / median** 啟發式，或
  **層次聚類 + 最優葉排序**，讓強連接的實體排在相鄰位置，ribbon 就不必橫跨整個圓。
- **Gansner & Koren《Improved Circular Layouts》**——降低圓形布局邊交叉與「墨水量」的經典參考。
- **聚合小流量**——把細小 ribbon 併成「其它」，或設最小閾值。
- **視覺手段**——ribbon 半透明、加大 group padding（間隙）、hover 高亮。

### 弧線圖（Arc）
節點排在一條直線上；雜亂**幾乎完全由線性節點順序決定**——排得好近乎無交叉，排得差全是大弧交叉。
- **一維排序優化**——**譜排序（Fiedler）**、**seriation**、或 **barycenter** 迭代。與 chord 同源，只是
  排在直線而非圓上。
- **兩側交替畫弧**——一半在基線上方、一半在下方，視覺密度減半。
- **依跨度／權重調節弧高與透明度**。

**實作（2026-07-08，`results/viz_codegen_arc/sonnet_arc_v2.py`）。** 排序目標從「最小化交叉」收緊為
「**最小化每條弧的跨度**」——同時顧**總跨度 `Σ|i−j|`（MinLA）**與**最大跨度 `max|i−j|`（帶寬）**。最大跨度
之所以關鍵：畫布高度由**最高的那條弧**決定，一條長程「橋」弧就把整圖撐成又高又空。採用的標準庫演算法：
**譜排序（Fiedler）依連通分量播種 + barycenter 精修**——每個分量按 Laplacian 第二小特徵值的特徵向量
排序（最小化 `Σ(x_i−x_j)²`，對長弧**平方懲罰**，以 `cI−L` 的確定性冪迭代求得），再用加權 barycenter 精修、
留總跨度最短的一輪。在 Mondial `borders`（n=169、326 邊）實測：交叉 **16772 → 985**，最長弧
**跨度 164 → 27**（從橫跨 97% 軸降到約 16%）；`merges_with`：交叉 **1264 → 159**。否決了兩種排法：純
**按度數**（最差，hub 堆一端）、**min-degree 起點的 RCM**（即使其它弧都短，仍可能留一條橫跨全軸的橋弧）。
冪迭代以固定去均值斜坡向量播種以保確定性。通用化寫入 `prompts/viz_codegen/chart_arc.md` step 4。

### 桑基圖（Sankey）
d3-sankey 內部其實**已在用 Sugiyama 框架**（依 FK 分層 → 層內排序 → 坐標分配）。雜亂通常是迭代不足或
參數未調。
- **增大層內排序迭代次數**——`.iterations(n)` 跑的就是 barycenter/median 松弛；多掃幾輪交叉更少。
- **調 `nodePadding` / `nodeWidth`**——拉開層內節點。
- **層內節點排序**——對上／下游鄰居做 median 啟發式。
- **處理環（cycle）**——反身關係可能形成環使 link 亂繞；先斷環（feedback arc set）再分層。
- **聚合小 link**。

## 本項目落地優先級（D3 v7）

按投入小 / 見效快排序：

1. **Force**——加 `d3.forceCollide()`；對稀疏圖加度數 / k-core 過濾。通常單此一項即解決大半雜亂。
2. **Arc 與 Chord**——實作一個**共用的節點排序模組**（barycenter 迭代或譜排序）；兩者排序問題同構
   （直線 vs 圓），一份演算法兩處用。此為兩圖交叉的根本解。
3. **Sankey**——先調 `.iterations()` 與 `nodePadding`（幾乎零成本）；不足再處理環。
4. **全局降密度**——四種圖統一加閾值過濾 + 小值聚合；任何布局在稀疏圖上都更乾淨。
5. **交互兜底**——hover 高亮相關節點/邊、其餘淡化（focus + context），即使仍有交叉，局部仍可讀。

## 一句話總結

四種圖的雜亂是同一個**圖交叉最小化**問題的不同表現。主線解法為：**節點排序（barycenter / 譜排序 /
seriation）+ 過濾與聚合降密度 + 布局後去重疊（forceCollide / VPSC）+ 邊捆綁**，其中 **Sugiyama 框架**
與 **barycenter/median 啟發式**貫穿始終。
