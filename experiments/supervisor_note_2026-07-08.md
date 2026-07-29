# Progress note — relationship-chart overlap reduction (2026-07-08)

## English

**Goal.** The four node-link relationship charts (force / arc / chord / Sankey) were
visually cluttered — heavy overlap and edge crossings. These are all the same underlying
problem: *graph crossing/overlap minimisation*, driven mainly by **node ordering**. I
reduced clutter chart-by-chart, encoded each fix as a general rule in the code-gen prompts,
and verified every change on the Mondial data.

**What changed / algorithms used.**

- **Arc diagram.** Replaced degree-based node order with a **crossing-minimising 1-D
  ordering**: a **spectral (Fiedler) seed** (eigenvector of the 2nd-smallest Laplacian
  eigenvalue, per connected component, via std-lib power iteration) refined by **barycentre
  iteration**. Objective tightened from "fewer crossings" to *minimise every arc's span*
  (Minimum Linear Arrangement + graph **bandwidth**), which also removes the giant "bridge"
  arc that made the figure bulky. *Result: crossings 16772 → 985; longest arc span 164 → 27.*
  Also fixed arc-height capping and a colour-visibility bug (near-white ramp).
- **Chord diagram.** Same spectral ordering wrapped onto the **circle**: Fiedler seed +
  **circular barycentre** (pull each node to the *angular* mean of its neighbours via
  `atan2`, handling wrap-around), selected by total circular span. *Result: crossings
  17674 → 1072 (~94 %).*
- **Sankey diagram.** Replaced single-pass ordering with **iterated two-layer barycentre**
  (classic **Sugiyama**), keeping the sweep with fewest crossings across two seeds; crossings
  counted exactly via a **Fenwick/BIT inversion count** (`O(E log|T|)`). *Result: crossings
  10348 → 3102 (~70 %).*
- **Force-directed graph.** Layout tuning: **group-separation force** (two-column bias for the
  bipartite case), **degree-scaled repulsion + capped range**, **padded collision**, dropping
  isolated nodes, and greedy label de-overlap; removed a hard viewport clamp that was defeating
  collision separation. Drag interaction preserved.

**Method.** Every renderer is a deterministic, standard-library Python program (the LLM
authors it once; rendering is reproducible). For each chart I wrote an improved version,
measured crossings before/after, then folded the fix back into the prompt as a *general,
data-agnostic* rule so future re-generations inherit it. A suite-wide light-theme rule was
also added for visual consistency.

**Common thread.** One family of methods — **seriation / ordering** (spectral Fiedler,
barycentre/median, Sugiyama) plus force-layout tuning — addresses all four charts, because
they are the same crossing-minimisation problem on a line, a circle, layers, or free 2-D.

---

## 中文

**目标。** 四种关系图（力导向 / 弧线 / 弦 / 桑基）视觉杂乱、连线大量重叠交叉。它们本质是**同一个问题：
图的交叉/重叠最小化**，主要由**节点排序**决定。我逐图降杂乱，并把每条修复以通用规则写回代码生成 prompt，
所有改动都在 Mondial 数据上做了验证。

**改动内容 / 所用算法。**

- **弧线图（Arc）。** 把「按度数排」换成**交叉最小化的一维排序**：**谱排序（Fiedler）种子**（Laplacian
  第二小特征值的特征向量，按连通分量、用标准库幂迭代求得）+ **barycenter 迭代**精修。目标从「少交叉」收紧为
  **最小化每条弧的跨度**（MinLA + 图**带宽**），顺带消除了让图显得笨重的「长桥弧」。*结果：交叉 16772 → 985；
  最长弧跨度 164 → 27。* 另修了弧高封顶与「颜色浅到看不见」的配色 bug。
- **弦图（Chord）。** 同一套谱排序**绕到圆上**：Fiedler 种子 + **圆形 barycenter**（用 `atan2` 把节点拉到
  邻居的**角度**均值，处理环绕），按圆周总跨度选优。*结果：交叉 17674 → 1072（约 94%）。*
- **桑基图（Sankey）。** 把单趟排序换成**迭代双层 barycenter**（经典 **Sugiyama**），多种子中按交叉数留最优；
  用 **Fenwick 树逆序对**精确数交叉（`O(E log|T|)`）。*结果：交叉 10348 → 3102（约 70%）。*
- **力导向图（Force）。** 布局调优：**分组分离力**（二部图左右分列）、**按度数缩放斥力 + 作用距离封顶**、
  **带 padding 的碰撞**、剔除孤立节点、贪心标签去重叠；移除了一处抵消碰撞分离的硬性裁剪。保留拖拽交互。

**方法。** 每个渲染器都是**确定性、纯标准库**的 Python 程序（LLM 一次性生成、之后渲染可复现）。每图我先写
改进版、量化前后交叉，再把修复以**通用、与数据无关**的规则写回 prompt，使后续重跑自动继承。另加了一条全套件
**浅色主题**规则以统一风格。

**共同主线。** 一族方法——**序列化/排序**（谱排序 Fiedler、barycenter/median、Sugiyama）配合力布局调参
——覆盖全部四种图，因为它们是同一个交叉最小化问题在直线、圆、分层、自由二维上的不同表现。
