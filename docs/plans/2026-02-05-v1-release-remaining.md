# V1.0.0 发布准备 — 剩余任务实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 创建完整测试数据集（12 座虚构桥梁、120+ chunks）和文档体系

**Architecture:**
- 测试数据采用 YAML 定义桥梁档案 + Markdown 文档的方式，便于人工编辑和审查
- 文档采用 Markdown 格式，包含 API 参考、入库指南、架构说明等

**Tech Stack:** YAML, Markdown, Python scripts

---

## 第一部分：测试数据集

### Task 1: 创建桥梁档案数据文件

**Files:**
- Create: `data/seed/bridges.yaml`

**Step 1: 创建 data/seed 目录**

```bash
mkdir -p data/seed
```

**Step 2: 编写桥梁档案 YAML**

创建 `data/seed/bridges.yaml`，包含 12 座虚构桥梁，覆盖所有桥型、材料、年代、区域组合：

```yaml
# 12 座虚构桥梁档案
# 覆盖：8种桥型 × 7种材料 × 8个年代 × 8个区域

bridges:
  # === 华北 ===
  - name: 青石关桥
    aliases: 青关桥
    location: 河北省张家口市 华北
    era: 明清
    bridge_type: 石拱桥
    material: 石
    function: 军事
    summary: 长城关隘处的石拱桥，连接内外交通要道

  - name: 永安木桥
    location: 山西省太原市 华北
    era: 宋元
    bridge_type: 梁桥
    material: 木
    function: 交通
    summary: 汾河古渡口的木梁桥，历经数百年风雨

  # === 华东 ===
  - name: 碧波廊桥
    aliases: 碧廊桥
    location: 浙江省丽水市 华东
    era: 明清
    bridge_type: 木拱桥
    material: 木
    function: 景观
    summary: 江南水乡的木拱廊桥，桥上设有长廊和茶亭

  - name: 钱塘铁桥
    location: 浙江省杭州市 华东
    era: 近现代
    bridge_type: 铁桥
    material: 铁
    function: 铁路
    summary: 钱塘江上的铁路桥，见证近代工业发展

  # === 华南 ===
  - name: 南海风雨桥
    aliases: 风雨桥
    location: 广西壮族自治区柳州市 华南
    era: 明清
    bridge_type: 梁桥
    material: 木
    function: 人行
    summary: 侗族风雨桥代表，桥上建有遮风挡雨的廊亭

  - name: 珠江悬索桥
    location: 广东省广州市 华南
    era: 当代
    bridge_type: 悬索桥
    material: 钢
    function: 公路
    summary: 珠江口的现代悬索桥，主跨超过千米

  # === 华中 ===
  - name: 洞庭浮桥
    location: 湖南省岳阳市 华中
    era: 秦汉
    bridge_type: 浮桥
    material: 木
    function: 军事
    summary: 古代洞庭湖畔的军用浮桥，以船连舟搭建

  - name: 长江斜拉桥
    location: 湖北省武汉市 华中
    era: 当代
    bridge_type: 斜拉桥
    material: 钢筋混凝土
    function: 综合交通
    summary: 武汉长江上的现代斜拉桥，双向八车道

  # === 西南 ===
  - name: 云渡桥
    aliases: 云桥
    location: 云南省大理市 西南
    era: 明清
    bridge_type: 石拱桥
    material: 石
    function: 交通
    summary: 横跨苍山溪流的三孔石拱桥，以云雾缭绕著称

  - name: 铁索寒桥
    aliases: 寒江桥
    location: 四川省甘孜州 西南
    era: 近现代
    bridge_type: 索桥
    material: 铁
    function: 交通
    summary: 高原峡谷铁索桥，冬季常有冰凌

  # === 西北 ===
  - name: 丝路古渡桥
    aliases: 古渡桥
    location: 甘肃省敦煌市 西北
    era: 隋唐
    bridge_type: 梁桥
    material: 石
    function: 交通
    summary: 丝绸之路上的石梁桥，连接东西方贸易

  # === 东北 ===
  - name: 冰城竹桥
    location: 黑龙江省哈尔滨市 东北
    era: 魏晋南北朝
    bridge_type: 梁桥
    material: 竹
    function: 人行
    summary: 北方少见的竹制桥梁，展现古人智慧
```

**Step 3: 验证 YAML 格式**

```bash
uv run python -c "import yaml; yaml.safe_load(open('data/seed/bridges.yaml'))" && echo "✓ Valid YAML"
```

**Step 4: Commit**

```bash
git add data/seed/bridges.yaml
git commit -m "feat: add seed bridge data (12 fictional bridges)"
```

---

### Task 2: 创建测试问题集

**Files:**
- Create: `data/seed/questions.yaml`

**Step 1: 编写测试问题 YAML**

创建 `data/seed/questions.yaml`，包含 20 个测试问题，覆盖各种查询场景：

```yaml
# 测试问题集
# 覆盖：Anchor / Concept / Analogy 三通道 + Facet 过滤

questions:
  # === Anchor 查询（指定桥梁） ===
  - question: 云渡桥的结构特点是什么？
    target_bridge: 云渡桥
    expected_channel: anchor
    description: 测试本桥资料检索

  - question: 青石关桥建于什么年代？
    target_bridge: 青石关桥
    expected_channel: anchor
    description: 测试历史信息检索

  - question: 碧波廊桥的桥上建筑有什么特点？
    target_bridge: 碧波廊桥
    expected_channel: anchor
    description: 测试构造细部检索

  - question: 铁索寒桥的主缆是什么材料？
    target_bridge: 铁索寒桥
    expected_channel: anchor
    description: 测试材料工艺检索

  # === Concept 查询（通用知识） ===
  - question: 石拱桥的主拱是如何建造的？
    expected_channel: concept
    description: 测试通用建造技术知识

  - question: 风雨桥的廊亭有什么功能？
    expected_channel: concept
    description: 测试通用功能知识

  - question: 悬索桥的主缆如何承受荷载？
    expected_channel: concept
    description: 测试通用结构原理

  - question: 浮桥是怎么固定的？
    expected_channel: concept
    description: 测试通用构造知识

  # === Analogy 查询（类比） ===
  - question: 有没有和云渡桥结构类似的桥？
    target_bridge: 云渡桥
    expected_channel: analogy
    description: 测试类比检索（同类型石拱桥）

  - question: 和碧波廊桥风格相近的桥有哪些？
    target_bridge: 碧波廊桥
    expected_channel: analogy
    description: 测试类比检索（木拱桥/景观功能）

  - question: 其他索桥和铁索寒桥有什么异同？
    target_bridge: 铁索寒桥
    expected_channel: analogy
    description: 测试类比检索（索桥类型）

  # === Facet 过滤 ===
  - question: 明清时期的石桥有哪些？
    expected_facets:
      era: 明清
      material: 石
    description: 测试年代+材料 facet 过滤

  - question: 西南地区有哪些桥梁？
    expected_facets:
      region: 西南
    description: 测试区域 facet 过滤

  - question: 现代的斜拉桥有哪些特点？
    expected_facets:
      era: 当代
      bridge_type: 斜拉桥
    description: 测试年代+桥型 facet 过滤

  - question: 有军事用途的桥梁有哪些？
    expected_facets:
      function: 军事
    description: 测试功能 facet 过滤

  # === 复杂查询 ===
  - question: 云渡桥和青石关桥哪个更古老？
    target_bridge: 云渡桥
    description: 测试比较类问题

  - question: 为什么南方多木桥而北方多石桥？
    expected_channel: concept
    description: 测试综合分析问题

  - question: 长江斜拉桥的建造难点是什么？
    target_bridge: 长江斜拉桥
    expected_channel: anchor
    description: 测试现代桥梁技术问题

  - question: 古代桥梁如何防洪？
    expected_channel: concept
    description: 测试通用工程知识

  - question: 铁路桥和公路桥的设计有什么区别？
    expected_channel: concept
    description: 测试功能差异知识
```

**Step 2: 验证 YAML 格式**

```bash
uv run python -c "import yaml; yaml.safe_load(open('data/seed/questions.yaml'))" && echo "✓ Valid YAML"
```

**Step 3: Commit**

```bash
git add data/seed/questions.yaml
git commit -m "feat: add seed questions (20 test queries)"
```

---

### Task 3: 创建桥梁文档（第一批 4 座）

**Files:**
- Create: `data/seed/documents/云渡桥.md`
- Create: `data/seed/documents/青石关桥.md`
- Create: `data/seed/documents/碧波廊桥.md`
- Create: `data/seed/documents/铁索寒桥.md`

**Step 1: 创建 documents 目录**

```bash
mkdir -p data/seed/documents
```

**Step 2: 创建云渡桥文档**

创建 `data/seed/documents/云渡桥.md`：

```markdown
---
bridge: 云渡桥
source_type: document
title: 云渡桥技术档案
---

# 概述

云渡桥位于云南省大理市苍山脚下，是一座典型的三孔石拱桥。因桥址常年云雾缭绕，故得名"云渡桥"。此桥始建于明代嘉靖年间，是连接苍山东西两侧的重要通道。

# 结构特点

## 主拱设计

云渡桥采用三孔石拱结构，中孔跨度最大，为 15.6 米，两侧边孔各 10.2 米。主拱采用半圆形拱券，矢跨比约为 1:2，这种设计既保证了结构稳定性，又便于行人和车辆通行。

拱券由当地青石砌筑而成，每块拱石经过精细加工，确保紧密咬合。拱圈厚度 0.8 米，由五层拱石叠砌而成。

## 桥墩构造

两座桥墩采用分水尖设计，上游端呈尖角形，可有效分流水势，减少洪水对桥墩的冲击。桥墩基础深入河床 3 米，采用松木桩加固。

## 桥面铺装

桥面宽 4.5 米，由青石板铺设。桥面两侧设有石质栏杆，栏杆柱头雕刻有祥云图案，与桥名相呼应。

# 历史沿革

## 始建背景

明代嘉靖年间（约1540年），为便利苍山两侧村落往来，当地官绅集资修建此桥。据《大理府志》记载，工程历时三年，动用石匠百余人。

## 历代修缮

- 清代康熙年间：加固桥墩基础
- 清代道光年间：重修桥面栏杆
- 民国时期：桥面局部修补
- 2010年：列入省级文物保护单位，进行全面修缮

# 地理环境

云渡桥所在区域属高原季风气候，每年5-10月为雨季。桥下溪流源自苍山积雪融水，夏季水量充沛。桥址海拔约2100米，早晚常有云雾笼罩。

# 文化价值

云渡桥不仅是交通设施，也是当地重要的文化景观。每逢节日，当地白族群众会在桥上举行祈福活动。桥旁立有明代修桥碑记，记载了建桥经过和捐资人名单。
```

**Step 3: 创建青石关桥文档**

创建 `data/seed/documents/青石关桥.md`：

```markdown
---
bridge: 青石关桥
source_type: document
title: 青石关桥技术档案
---

# 概述

青石关桥位于河北省张家口市境内，是长城防线上的一座重要军事桥梁。此桥建于明代，用于连接长城内外的交通要道，历史上曾是兵家必争之地。

# 结构特点

## 主拱设计

青石关桥为单孔石拱桥，跨度 12 米，采用尖拱形式。尖拱设计使桥梁在承受重载时更加稳定，适合军事运输需要。拱券由当地青石砌筑，石块尺寸较大，最重者达500公斤。

## 防御设施

桥头两端原设有关卡，可控制人员和物资出入。桥面两侧的石栏杆高度为1.2米，比一般桥梁更高，兼具防护功能。

## 桥台构造

桥台直接嵌入两岸岩石之中，与山体融为一体。这种设计既节省了材料，又提高了桥梁的整体稳定性。

# 历史沿革

## 始建背景

明代为加强长城防御，在各关隘修建配套设施。青石关桥建于明代嘉靖年间，与长城敌台同期修建，是长城防御体系的重要组成部分。

## 军事历史

- 明代：驻军守卫，控制关口通行
- 清代：军事功能减弱，转为民用
- 抗日战争时期：曾发生激烈战斗

# 地理环境

青石关桥位于太行山脉北段，地势险峻。桥下为季节性山洪沟，雨季水流湍急。桥址海拔约1200米，冬季严寒，气温常低于-20°C。
```

**Step 4: 创建碧波廊桥文档**

创建 `data/seed/documents/碧波廊桥.md`：

```markdown
---
bridge: 碧波廊桥
source_type: document
title: 碧波廊桥技术档案
---

# 概述

碧波廊桥位于浙江省丽水市山区，是一座典型的江南木拱廊桥。此桥以其精美的木雕和独特的廊亭建筑闻名，是浙南木拱桥的代表作之一。

# 结构特点

## 木拱构造

碧波廊桥采用编木拱结构，主拱由数十根圆木相互穿插编织而成，形成稳定的拱形承重系统。这种"编梁木拱"技术是中国独有的桥梁形式，被誉为"桥梁活化石"。

主拱跨度18米，矢高6米，由杉木构成。每根拱木直径约30厘米，通过榫卯连接，不使用铁钉。

## 廊亭建筑

桥上建有双层廊亭，下层为通道，上层为阁楼。廊亭采用穿斗式木构架，屋顶为重檐歇山顶，飞檐翘角，造型优美。

廊内设有长椅供行人休息，两侧开有花窗，可观赏溪流风光。

## 木雕装饰

廊桥上的木雕极为精美，包括：
- 梁枋上的花卉图案
- 撑拱上的龙凤雕刻
- 门窗上的镂空花格

# 历史沿革

## 始建背景

清代乾隆年间，当地乡绅为方便村民出行，集资修建此桥。据碑文记载，工程由著名桥匠张氏主持，历时两年完工。

## 文化活动

碧波廊桥不仅是交通设施，也是当地的公共活动空间：
- 雨天可供村民避雨休息
- 节日时举办庙会活动
- 夏日傍晚是乘凉聚会场所

# 地理环境

碧波廊桥横跨一条山间溪流，两岸植被茂密。此地属亚热带季风气候，温暖湿润，适合木材长期保存。桥下溪水清澈，因波光粼粼而得名"碧波"。
```

**Step 5: 创建铁索寒桥文档**

创建 `data/seed/documents/铁索寒桥.md`：

```markdown
---
bridge: 铁索寒桥
source_type: document
title: 铁索寒桥技术档案
---

# 概述

铁索寒桥位于四川省甘孜藏族自治州，是一座横跨高原峡谷的铁索桥。因冬季桥上常挂冰凌，寒风刺骨，故名"铁索寒桥"。此桥是连接藏区与内地的重要通道。

# 结构特点

## 索桥系统

铁索寒桥采用双索承重结构，两根主索平行布置，间距2米。主索由熟铁锻造，每根主索由数百个铁环相连而成，全长约80米。

主索两端锚固于峡谷两侧的岩壁之中，锚固深度达5米，确保主索在强风和重载下不会松动。

## 桥面构造

桥面由木板铺设，宽度约1.5米，仅供行人和牲畜通行。木板通过铁链悬挂于主索之下，随风晃动是铁索桥的特点。

桥面两侧设有扶手索，供行人抓握，增加通行安全性。

## 防护措施

为防止主索生锈，每年雨季前都要涂抹桐油保护。冬季需定期清除冰凌，防止过重的冰层压断木板。

# 历史沿革

## 始建背景

民国初年，为改善藏区交通条件，当地政府组织修建此桥。铁索由成都铁匠铺锻造，运输至工地耗时数月。

## 使用历史

- 民国时期：主要运输茶叶、盐巴等物资
- 新中国成立后：成为公路未通前的主要通道
- 现代：作为文物保护，仅供游客参观

# 地理环境

铁索寒桥所在峡谷海拔约3500米，属高原气候。冬季气温可低至-25°C，河谷中常有大风。桥下河流为雅砻江支流，夏季水流湍急，冬季部分结冰。

# 通行安全

由于桥面晃动较大，通行时需注意：
- 保持均匀步速，避免急跑
- 遇强风时暂停通行
- 负重不宜超过50公斤
```

**Step 6: Commit**

```bash
git add data/seed/documents/
git commit -m "feat: add seed documents (batch 1: 4 bridges)"
```

---

### Task 4: 创建桥梁文档（第二批 4 座）

**Files:**
- Create: `data/seed/documents/永安木桥.md`
- Create: `data/seed/documents/钱塘铁桥.md`
- Create: `data/seed/documents/南海风雨桥.md`
- Create: `data/seed/documents/珠江悬索桥.md`

**Step 1: 创建永安木桥文档**

创建 `data/seed/documents/永安木桥.md`：

```markdown
---
bridge: 永安木桥
source_type: document
title: 永安木桥技术档案
---

# 概述

永安木桥位于山西省太原市汾河古渡口，是一座传统木梁桥。此桥始建于宋代，历经数百年风雨，多次重建，是汾河流域重要的交通设施。

# 结构特点

## 梁桥结构

永安木桥采用多跨简支木梁结构，共有七跨，每跨跨度约8米。主梁由粗壮的松木制成，直径约40厘米，两根并列承重。

## 桥墩设计

桥墩采用木排架结构，由多根立柱和横撑组成。立柱底部打入河床，形成稳定的基础。木墩外侧包裹石块，增加抗冲刷能力。

## 桥面铺装

桥面宽3.5米，由厚木板横向铺设。两侧设有简易木栏杆，高度约0.9米。

# 历史沿革

## 始建背景

宋代太原城外汾河渡口繁忙，为方便商旅往来，官府出资修建木桥。据《太原府志》记载，此桥"便民利商，功德无量"。

## 历代重建

由于木材易腐，此桥历史上多次重建：
- 元代：洪水冲毁后重建
- 明代：扩建加宽
- 清代：两次修缮
- 现代：按原貌复建

# 地理环境

永安木桥位于汾河中游，两岸地势平坦。汾河水量季节性变化明显，夏秋多洪水，冬春水位较低。
```

**Step 2: 创建钱塘铁桥文档**

创建 `data/seed/documents/钱塘铁桥.md`：

```markdown
---
bridge: 钱塘铁桥
source_type: document
title: 钱塘铁桥技术档案
---

# 概述

钱塘铁桥位于浙江省杭州市，是一座近代铁路桥。此桥建于清末民初，是钱塘江上最早的铁路桥梁，见证了中国近代工业发展历程。

# 结构特点

## 桁架结构

钱塘铁桥采用下承式钢桁架结构，共有12孔，每孔跨度约50米。桁架高度6米，由角钢和槽钢铆接而成。

## 桥墩设计

桥墩采用钢筋混凝土结构，这在当时是先进技术。桥墩基础深入河床以下15米，采用沉井施工法建造。

## 铁路设施

桥上铺设单线铁轨，轨距为标准轨1435毫米。桥面两侧设有人行道，供维护人员通行。

# 历史沿革

## 建造背景

清末，为修建沪杭铁路，需在钱塘江上架桥。工程由中外工程师联合设计，使用进口钢材，历时四年完工。

## 历史事件

- 民国时期：作为沪杭铁路咽喉，战略地位重要
- 抗日战争：为阻止日军南下，曾被炸断
- 新中国成立后：修复通车，继续使用

# 地理环境

钱塘铁桥位于钱塘江下游，此处江面宽约1公里。钱塘江以涌潮闻名，设计时充分考虑了潮汐和涌潮对桥梁的影响。

# 工程技术

## 施工难点

- 钱塘江水深流急，桥墩施工困难
- 涌潮期间无法作业，工期受限
- 软土地基处理复杂

## 技术创新

- 首次在中国使用沉井法建造深水桥墩
- 采用气压沉箱技术
- 引进先进的钢材铆接工艺
```

**Step 3: 创建南海风雨桥文档**

创建 `data/seed/documents/南海风雨桥.md`：

```markdown
---
bridge: 南海风雨桥
source_type: document
title: 南海风雨桥技术档案
---

# 概述

南海风雨桥位于广西壮族自治区柳州市，是一座典型的侗族风雨桥。此桥集交通、休憩、集会功能于一体，是侗族建筑文化的代表作。

# 结构特点

## 木梁结构

南海风雨桥采用木梁简支结构，共三跨，每跨跨度约12米。主梁由整根杉木制成，直径约50厘米，承载能力强。

## 廊亭建筑

桥上建有连续廊亭，全长约40米。廊亭采用穿斗式木构架，屋顶为悬山顶，覆盖青瓦。中部设有鼓楼式高塔，高约15米，是全桥的标志性建筑。

## 木雕彩绘

廊桥装饰极为丰富：
- 檐口有彩绘图案
- 梁枋雕刻龙凤花草
- 廊内绘有历史故事壁画

# 历史沿革

## 始建背景

清代雍正年间，侗族村民为方便出行和集会，集资修建此桥。工程由侗族工匠主持，全部采用传统榫卯工艺，不用一颗铁钉。

## 文化功能

南海风雨桥不仅是交通设施，更是重要的公共活动空间：
- 雨天避雨休息
- 节日举办芦笙会
- 青年男女对歌择偶
- 长者议事商量村务

# 地理环境

南海风雨桥横跨柳江支流，两岸是侗族村寨。此地属亚热带季风气候，雨水充沛，故需建造遮风挡雨的廊桥。
```

**Step 4: 创建珠江悬索桥文档**

创建 `data/seed/documents/珠江悬索桥.md`：

```markdown
---
bridge: 珠江悬索桥
source_type: document
title: 珠江悬索桥技术档案
---

# 概述

珠江悬索桥位于广东省广州市，是一座现代化大型悬索桥。此桥是珠江口重要的公路通道，代表了当代中国桥梁建设的先进水平。

# 结构特点

## 悬索系统

珠江悬索桥主跨1200米，是同期建成的最长悬索桥之一。两根主缆直径约1米，由数万根高强度钢丝组成，总重量超过2万吨。

主缆通过索夹与吊索连接，吊索间距约15米，将桥面荷载传递到主缆上。

## 桥塔设计

两座主塔高度达260米，采用钢筋混凝土结构。塔身呈门形，线条流畅，兼顾结构功能与美学效果。

塔顶设有航标灯，夜间为船只提供导航。

## 桥面系统

桥面为钢箱梁结构，宽度38米，设双向八车道。钢箱梁采用流线型截面，减小风阻，提高抗风稳定性。

# 历史沿革

## 建设背景

为缓解珠三角地区交通压力，促进区域经济发展，21世纪初启动建设。工程采用国际招标，汇集了国内外顶尖桥梁专家。

## 建设过程

- 2015年：正式开工
- 2018年：主塔封顶
- 2020年：主缆架设完成
- 2022年：建成通车

# 地理环境

珠江悬索桥位于珠江口，此处江面宽阔，通航繁忙。设计时充分考虑了大型船舶通行需要，主跨通航净高达65米。

# 工程技术

## 抗风设计

珠江口台风频繁，桥梁抗风是关键技术挑战。通过风洞试验优化截面设计，安装调质阻尼器，确保桥梁在强风下稳定。

## 防腐措施

海洋环境腐蚀性强，桥梁采用多重防腐措施：
- 钢结构涂装重防腐涂料
- 主缆采用镀锌钢丝
- 混凝土结构提高密实度
```

**Step 5: Commit**

```bash
git add data/seed/documents/
git commit -m "feat: add seed documents (batch 2: 4 bridges)"
```

---

### Task 5: 创建桥梁文档（第三批 4 座）

**Files:**
- Create: `data/seed/documents/洞庭浮桥.md`
- Create: `data/seed/documents/长江斜拉桥.md`
- Create: `data/seed/documents/丝路古渡桥.md`
- Create: `data/seed/documents/冰城竹桥.md`

**Step 1: 创建洞庭浮桥文档**

创建 `data/seed/documents/洞庭浮桥.md`：

```markdown
---
bridge: 洞庭浮桥
source_type: document
title: 洞庭浮桥技术档案
---

# 概述

洞庭浮桥位于湖南省岳阳市洞庭湖畔，是古代军用浮桥的典型代表。此桥以船连舟搭建，可快速架设和撤除，在古代军事行动中发挥重要作用。

# 结构特点

## 浮桥系统

洞庭浮桥采用船桥式结构，由数十艘木船并排连接而成。每艘船长约8米，宽约2米，船与船之间用铁链和绳索固定。

## 桥面铺设

桥面由厚木板铺设在船顶，形成连续的通道。为增加稳定性，木板与船体用铁钉固定，并在两侧设置简易栏杆。

## 锚固系统

浮桥两端分别锚固于岸边，中间通过多个锚点固定船体位置。铁锚重约500公斤，锚绳为粗麻绳，直径约5厘米。

# 历史沿革

## 始建背景

秦汉时期，洞庭湖区是南北交通要道。为便于军队渡湖，官府在此设置浮桥。据《汉书》记载，此桥"可容车马万人"。

## 军事用途

- 秦代：统一战争中用于南征
- 汉代：平定南方叛乱时使用
- 三国时期：吴国水军重要通道

# 地理环境

洞庭湖水域辽阔，水位季节性变化大。浮桥需根据水位调整锚绳长度，洪水期间有时需要临时撤除。

# 架设技术

## 快速架设

浮桥可在数小时内完成架设：
1. 船只排列就位
2. 用铁链连接船体
3. 铺设桥面木板
4. 固定锚点

## 撤除方法

撤除时按相反顺序进行，船只可另作他用。
```

**Step 2: 创建长江斜拉桥文档**

创建 `data/seed/documents/长江斜拉桥.md`：

```markdown
---
bridge: 长江斜拉桥
source_type: document
title: 长江斜拉桥技术档案
---

# 概述

长江斜拉桥位于湖北省武汉市，是一座现代化斜拉桥。此桥横跨长江，是武汉城市交通网络的重要组成部分，设计双向八车道，通行能力强大。

# 结构特点

## 斜拉索系统

长江斜拉桥采用双塔双索面斜拉结构，主跨618米。每座桥塔两侧各有28对斜拉索，呈扇形布置，将桥面荷载传递到桥塔。

斜拉索由高强度钢绞线组成，外包PE护套，防止腐蚀。

## 桥塔设计

两座主塔高度200米，采用钻石型混凝土塔柱。塔柱截面从下向上逐渐收窄，既美观又节省材料。

## 桥面系统

主梁采用钢-混凝土组合结构，上层为预应力混凝土桥面板，下层为钢箱梁。这种组合结构兼具刚度和韧性。

桥面总宽度42米，设双向八车道，两侧各有人行道。

# 历史沿革

## 建设背景

21世纪初，武汉城市发展迅速，过江交通需求剧增。经过多方案比选，决定建设这座大跨度斜拉桥。

## 建设过程

- 2016年：开工建设
- 2019年：桥塔封顶
- 2021年：主梁合龙
- 2023年：建成通车

# 地理环境

长江斜拉桥位于长江中游，此处江面宽约1.5公里，水深达30米。设计时充分考虑了长江洪水和大型船舶通航需要。

# 工程技术

## 建造难点

- 深水桥墩基础施工
- 超高桥塔混凝土浇筑
- 大跨度主梁悬臂拼装
- 斜拉索精确定位张拉

## 创新技术

- 采用智能张拉系统，斜拉索张力误差小于1%
- 使用BIM技术进行全过程管理
- 应用北斗定位系统监测桥梁变形
```

**Step 3: 创建丝路古渡桥文档**

创建 `data/seed/documents/丝路古渡桥.md`：

```markdown
---
bridge: 丝路古渡桥
source_type: document
title: 丝路古渡桥技术档案
---

# 概述

丝路古渡桥位于甘肃省敦煌市，是丝绸之路上的重要石梁桥。此桥始建于隋唐时期，是连接东西方贸易的交通要道，见证了千年丝路繁华。

# 结构特点

## 石梁结构

丝路古渡桥采用多跨石梁结构，共五跨，每跨跨度约6米。主梁由整块花岗岩加工而成，每根石梁重约3吨。

## 桥墩设计

桥墩用条石砌筑，呈矩形截面。墩身上游端略呈尖角，减少水流冲击。桥墩基础为毛石混凝土，深入河床约2米。

## 桥面构造

桥面宽4米，由青石板铺设。两侧设有石质栏杆，栏杆上雕刻有胡人和骆驼图案，反映丝路贸易特色。

# 历史沿革

## 始建背景

隋唐时期，敦煌是丝绸之路重镇。为便于商旅渡河，官府在此修建石桥。据敦煌文书记载，此桥"商贾络绎，骆驼成群"。

## 丝路见证

- 唐代：丝路贸易鼎盛期，每日通行商队数十
- 宋代：贸易衰落，桥梁疏于维护
- 元代：蒙古西征，桥梁重新繁忙
- 明代：海路兴起，陆路衰落

# 地理环境

丝路古渡桥横跨敦煌绿洲中的一条季节性河流。此地气候干旱，年降水不足50毫米，但春季雪山融水会带来较大水流。

# 文化意义

丝路古渡桥是中西文化交流的实物见证。桥上栏杆的雕刻融合了中原和西域艺术风格，具有重要的历史和艺术价值。
```

**Step 4: 创建冰城竹桥文档**

创建 `data/seed/documents/冰城竹桥.md`：

```markdown
---
bridge: 冰城竹桥
source_type: document
title: 冰城竹桥技术档案
---

# 概述

冰城竹桥位于黑龙江省哈尔滨市，是北方地区罕见的竹制桥梁。此桥始建于魏晋南北朝时期，展现了古人因地制宜的建桥智慧。

# 结构特点

## 竹梁结构

冰城竹桥采用竹梁简支结构，共三跨，每跨跨度约5米。主梁由多根粗壮毛竹捆扎而成，每束竹梁直径约30厘米。

## 连接方式

竹构件之间用竹篾和麻绳捆扎，不使用铁钉。这种柔性连接使桥梁具有一定弹性，能够适应温度变化引起的材料伸缩。

## 桥面铺设

桥面由竹排铺设，竹片横向排列，用竹篾编织固定。两侧设有竹制栏杆，高度约0.8米。

# 历史沿革

## 始建背景

魏晋南北朝时期，东北地区与南方交流增多，南方的竹编技术传入北方。当地工匠利用进口竹材，尝试建造竹桥。

## 特殊挑战

- 北方寒冷干燥，竹材易开裂
- 需定期涂抹桐油保护
- 冬季需清除积雪和冰凌

# 地理环境

冰城竹桥横跨松花江支流。此地冬季漫长严寒，气温可低至-30°C，对竹材保护是极大考验。

# 技术价值

冰城竹桥证明了古代工匠对材料特性的深刻理解。他们通过特殊的加工和保护措施，使竹材在严寒环境中也能长期使用，展现了因材施工的智慧。

## 保护措施

- 秋季涂抹防裂油
- 冬季覆盖稻草保温
- 春季检查更换损坏竹构件
```

**Step 5: Commit**

```bash
git add data/seed/documents/
git commit -m "feat: add seed documents (batch 3: 4 bridges)"
```

---

### Task 6: 创建种子数据加载脚本

**Files:**
- Modify: `scripts/seed_test_data.py`

**Step 1: 更新种子脚本以读取 YAML 和 Markdown 文件**

将 `scripts/seed_test_data.py` 更新为从 `data/seed/` 目录加载数据：

```python
"""Seed test data for integration testing.

Loads bridge data from data/seed/bridges.yaml and documents from data/seed/documents/*.md
"""
import asyncio
from pathlib import Path

import yaml
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import load_taxonomy
from app.models import Base, Bridge, Chunk, Source, TaxonomyNode
from app.providers import ZhipuProvider
from app.services.chunker import SemanticChunker
from app.services.context_enricher import ContextEnricher
from app.services.markdown_parser import parse_markdown
from app.services.tagger import MetadataTagger
from app.services.tokenizer import Tokenizer

SEED_DIR = Path(__file__).parent.parent / "data" / "seed"


def get_taxonomy_lvl2_map() -> dict[str, list[str]]:
    """Convert taxonomy to lvl1 -> [lvl2] mapping for tagger."""
    taxonomy = load_taxonomy()
    return {lvl1: list(lvl2_dict.keys()) for lvl1, lvl2_dict in taxonomy.items()}


def seed_taxonomy(session: Session) -> None:
    """Seed taxonomy nodes from config/taxonomy.yaml."""
    taxonomy = load_taxonomy()
    nodes = []
    for lvl1, lvl2_dict in taxonomy.items():
        for lvl2, lvl3_list in lvl2_dict.items():
            for lvl3 in lvl3_list:
                nodes.append(TaxonomyNode(lvl1=lvl1, lvl2=lvl2, lvl3=lvl3))
    session.add_all(nodes)
    print(f"  - {len(nodes)} taxonomy nodes")


def seed_bridges(session: Session) -> dict[str, Bridge]:
    """Seed bridges from data/seed/bridges.yaml."""
    bridges_file = SEED_DIR / "bridges.yaml"
    if not bridges_file.exists():
        print("  - bridges.yaml not found, skipping")
        return {}

    with open(bridges_file, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    bridge_map = {}
    for b in data.get("bridges", []):
        bridge = Bridge(
            name=b["name"],
            aliases=b.get("aliases"),
            location=b.get("location"),
            era=b.get("era"),
            bridge_type=b.get("bridge_type"),
            material=b.get("material"),
            function=b.get("function"),
            summary=b.get("summary"),
        )
        session.add(bridge)
        session.flush()
        bridge_map[b["name"]] = bridge

    print(f"  - {len(bridge_map)} bridges")
    return bridge_map


async def seed_documents(
    session: Session,
    bridge_map: dict[str, Bridge],
    use_llm: bool = False,
) -> int:
    """Seed chunks from data/seed/documents/*.md.

    Args:
        session: Database session
        bridge_map: Map of bridge name to Bridge object
        use_llm: If True, use LLM for chunking/tagging/enrichment (slow but realistic)
                If False, use simple splitting (fast for testing)
    """
    docs_dir = SEED_DIR / "documents"
    if not docs_dir.exists():
        print("  - documents/ not found, skipping")
        return 0

    tokenizer = Tokenizer(user_dict_path="data/bridge_terms.txt")
    chunk_count = 0

    if use_llm:
        # Full LLM pipeline (slow but realistic)
        provider = ZhipuProvider()
        chunker = SemanticChunker(
            provider=provider,
            min_chunk_size=200,
            max_chunk_size=500,
            similarity_threshold=0.5,
        )
        tagger = MetadataTagger(provider=provider, taxonomy_lvl2=get_taxonomy_lvl2_map())
        enricher = ContextEnricher(provider=provider)
    else:
        # Simple splitting (fast for testing)
        provider = None
        chunker = None
        tagger = None
        enricher = None

    for md_file in sorted(docs_dir.glob("*.md")):
        content = md_file.read_text(encoding="utf-8")
        doc = parse_markdown(content)

        bridge_name = doc.frontmatter.get("bridge")
        title = doc.frontmatter.get("title", md_file.stem)
        source_type = doc.frontmatter.get("source_type", "document")

        # Get bridge
        bridge = bridge_map.get(bridge_name)
        bridge_id = bridge.id if bridge else None

        # Create source
        source = Source(type=source_type, title=title)
        session.add(source)
        session.flush()

        # Process sections
        if use_llm and chunker:
            # Use full LLM pipeline
            text_parts = []
            for section in doc.sections:
                heading = "#" * section.level + " " + section.title
                text_parts.append(f"{heading}\n\n{section.content}")
            full_text = "\n\n".join(text_parts)

            chunk_results = await chunker.chunk(full_text)
            for i, cr in enumerate(chunk_results):
                # Enrich context
                contextual_text = ""
                try:
                    surrounding = [chunk_results[i-1].content] if i > 0 else None
                    ctx = await enricher.enrich(
                        content=cr.content,
                        source_title=title,
                        section_title=cr.section_title,
                        surrounding_chunks=surrounding,
                    )
                    contextual_text = ctx.contextual_text or ""
                except Exception:
                    pass

                # Tag
                tag = await tagger.tag(cr.content)

                # Embed
                search_text = f"{contextual_text}\n\n{cr.content}" if contextual_text else cr.content
                embeddings = await provider.embed([search_text])
                embedding = embeddings[0] if embeddings else [0.0] * 2048

                chunk = Chunk(
                    source_id=source.id,
                    content=cr.content,
                    section_title=cr.section_title,
                    contextual_text=contextual_text,
                    search_text=search_text,
                    lvl1=tag.lvl1,
                    lvl2=tag.lvl2,
                    lvl3=tag.lvl3,
                    bridge_id=bridge_id,
                    embedding=embedding,
                )
                session.add(chunk)
                chunk_count += 1
        else:
            # Simple splitting by section (fast)
            for section in doc.sections:
                search_text = f"[{section.title}] {section.content}"
                # Use deterministic fake embedding based on content hash
                fake_emb = [float(hash(search_text + str(i)) % 1000) / 1000 for i in range(2048)]

                chunk = Chunk(
                    source_id=source.id,
                    content=section.content,
                    section_title=section.title,
                    contextual_text="",
                    search_text=search_text,
                    lvl1="形制与技术",  # Default
                    lvl2="结构体系",
                    bridge_id=bridge_id,
                    embedding=fake_emb,
                )
                session.add(chunk)
                chunk_count += 1

        print(f"    - {md_file.name}: processed")

    session.flush()

    # Populate tsvector
    chunks = session.query(Chunk).filter(Chunk.source_id >= 1).all()
    mappings = [
        {
            "id": c.id,
            "tsv_text": tokenizer.to_tsvector_text(c.search_text or c.content),
        }
        for c in chunks
    ]
    if mappings:
        session.execute(
            text("UPDATE chunks SET tsv = to_tsvector('simple', :tsv_text) WHERE id = :id"),
            mappings,
        )

    print(f"  - {chunk_count} chunks total")
    return chunk_count


def seed(use_llm: bool = False):
    """Seed all test data.

    Args:
        use_llm: If True, use LLM for realistic chunking/tagging (slow)
    """
    engine = create_engine(settings.database_url)

    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()

    Base.metadata.create_all(engine)

    with Session(engine) as session:
        print("Seeding test data...")

        # Taxonomy
        seed_taxonomy(session)

        # Bridges
        bridge_map = seed_bridges(session)

        # Documents
        asyncio.run(seed_documents(session, bridge_map, use_llm=use_llm))

        session.commit()
        print("\nTest data seeded successfully!")


if __name__ == "__main__":
    import sys
    use_llm = "--llm" in sys.argv
    if use_llm:
        print("Using LLM for chunking/tagging (this may take a while)...")
    seed(use_llm=use_llm)
```

**Step 2: 测试脚本可导入**

```bash
uv run python -c "from scripts.seed_test_data import seed; print('✓ seed_test_data imports')"
```

**Step 3: Commit**

```bash
git add scripts/seed_test_data.py
git commit -m "feat: update seed script to load from YAML/Markdown files"
```

---

## 第二部分：文档

### Task 7: 创建 API 文档

**Files:**
- Create: `docs/api/v1.md`

**Step 1: 创建 docs/api 目录**

```bash
mkdir -p docs/api
```

**Step 2: 编写 API 文档**

创建 `docs/api/v1.md`：

```markdown
# API V1 参考文档

## 基础信息

- **Base URL:** `/api/v1`
- **Content-Type:** `application/json`

---

## 端点列表

| 端点 | 方法 | 描述 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/api/v1/ask` | POST | 问答 |
| `/api/v1/ingest` | POST | 入库 |

---

## GET /health

健康检查端点，用于负载均衡探针。

### 响应

```json
{
  "status": "ok"
}
```

---

## POST /api/v1/ask

根据问题检索相关知识并生成回答。

### 请求体

```json
{
  "question": "赵州桥的结构特点是什么？",
  "target_bridge_id": 1,
  "context": {
    "bridge_id": 1,
    "lvl1": "形制与技术",
    "lvl2": "结构体系",
    "lvl3": "拱桥结构"
  }
}
```

| 字段 | 类型 | 必填 | 描述 |
|------|------|------|------|
| `question` | string | 是 | 用户问题 |
| `target_bridge_id` | int | 否 | 目标桥梁 ID，用于 Anchor 检索 |
| `context` | object | 否 | 过滤条件 |

### 响应体

```json
{
  "summary": "赵州桥是一座敞肩式石拱桥...",
  "details": "详细说明...",
  "analogy": "类似于卢沟桥的设计...",
  "citations": [
    {
      "chunk_id": 1,
      "source_title": "赵州桥技术档案",
      "page_range": null
    }
  ],
  "sources": ["赵州桥技术档案"],
  "confidence": {
    "level": "high",
    "reason": "本桥资料有直接相关内容"
  },
  "evidence_groups": {
    "anchor": [...],
    "concept": [...],
    "analogy": [...]
  },
  "degraded": null
}
```

| 字段 | 类型 | 描述 |
|------|------|------|
| `summary` | string | 简要回答（1-3 句） |
| `details` | string | 详细说明 |
| `analogy` | string\|null | 类比案例说明 |
| `citations` | array | 引用列表 |
| `sources` | array | 来源标题列表 |
| `confidence` | object | 置信度评估 |
| `evidence_groups` | object | 证据分组 |
| `degraded` | array\|null | 降级标志 |

### 置信度级别

| 级别 | 含义 |
|------|------|
| `high` | 本桥资料有直接相关内容 |
| `medium` | 通用知识有相关内容，但本桥资料不足 |
| `low` | 证据不足或只有间接相关内容 |

### 降级标志

| 标志 | 含义 |
|------|------|
| `facet` | Facet 提取失败 |
| `retrieval` | 检索过程出错 |
| `empty_evidence` | 未找到相关证据 |

---

## POST /api/v1/ingest

导入 Markdown 格式文档到知识库。

### 请求体

```json
{
  "content": "---\nbridge: 赵州桥\ntitle: 赵州桥技术档案\n---\n\n# 概述\n\n赵州桥是...",
  "source_type": "document"
}
```

| 字段 | 类型 | 必填 | 描述 |
|------|------|------|------|
| `content` | string | 是 | Markdown 文档内容 |
| `source_type` | string | 否 | 来源类型，默认 `document` |

### Markdown 格式

```markdown
---
bridge: 桥梁名称
source_type: document
title: 文档标题
---

# 章节标题

正文内容...

## 子章节

更多内容...
```

### 响应体

```json
{
  "source_id": 1,
  "bridge_name": "赵州桥",
  "title": "赵州桥技术档案",
  "chunk_count": 5,
  "chunks": [
    {
      "content_preview": "赵州桥是一座敞肩式石拱桥...",
      "lvl1": "形制与技术",
      "lvl2": "结构体系",
      "bridge_name": "赵州桥"
    }
  ]
}
```

---

## 错误响应

### 422 Validation Error

请求参数校验失败：

```json
{
  "detail": [
    {
      "loc": ["body", "question"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

### 400 Bad Request

业务逻辑错误：

```json
{
  "detail": "No content found in document"
}
```

### 500 Internal Server Error

服务器内部错误：

```json
{
  "detail": "Internal server error"
}
```
```

**Step 3: Commit**

```bash
git add docs/api/
git commit -m "docs: add API v1 reference documentation"
```

---

### Task 8: 创建入库指南

**Files:**
- Create: `docs/ingest-guide.md`

**Step 1: 编写入库指南**

创建 `docs/ingest-guide.md`：

```markdown
# 入库指南

本指南说明如何将桥梁知识资料导入 Bridge RAG 系统。

## 文档格式

### Markdown + YAML Front Matter

所有入库资料采用 Markdown 格式，并在文件开头使用 YAML front matter 声明元数据：

```markdown
---
bridge: 赵州桥
source_type: document
title: 赵州桥研究资料
---

# 概述

赵州桥位于河北省赵县...

# 结构特点

## 主拱设计

采用敞肩式结构...
```

### Front Matter 字段

| 字段 | 类型 | 必填 | 描述 |
|------|------|------|------|
| `bridge` | string | 建议 | 关联的桥梁名称，用于 Anchor 检索 |
| `source_type` | string | 否 | 来源类型：`document`、`note`、`web` 等 |
| `title` | string | 否 | 文档标题，默认使用文件名 |

## 章节结构

### 推荐的章节划分

按桥梁知识的逻辑结构组织章节：

```markdown
# 概述
桥梁基本介绍...

# 结构特点
## 主拱/主梁设计
## 桥墩构造
## 桥面系统

# 历史沿革
## 始建背景
## 修缮记录

# 地理环境
地形、气候、水文...

# 文化价值
历史意义、保护情况...
```

### 章节层级

- 使用 `#` 标记一级章节
- 使用 `##` 标记二级章节
- 建议不超过三级嵌套

## 入库方式

### API 入库

```bash
curl -X POST http://localhost:8000/api/v1/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "content": "---\nbridge: 赵州桥\ntitle: 测试\n---\n\n# 概述\n\n内容...",
    "source_type": "document"
  }'
```

### 批量入库

将多个 Markdown 文件放入目录，使用脚本批量导入：

```bash
# 将文件放入 data/seed/documents/
# 运行种子脚本
python scripts/seed_test_data.py --llm
```

## 处理流程

入库时系统自动执行以下处理：

1. **解析 Front Matter** - 提取桥梁名称、标题等元数据
2. **章节分割** - 按标题级别分割文档
3. **语义切块** - 将长章节切分为 200-500 字的块
4. **上下文增强** - 为每个块生成上下文描述
5. **Taxonomy 标注** - 自动分类到三级知识体系
6. **向量化** - 生成 2048 维 embedding
7. **FTS 索引** - 建立全文搜索索引

## 最佳实践

### 内容建议

- 每个文档聚焦一座桥梁
- 章节划分清晰，便于切块
- 避免过长的连续段落
- 关键数据用数字而非文字描述

### 避免的问题

- ❌ 不要在一个文档中混合多座桥梁的信息
- ❌ 不要使用纯图片内容（OCR 暂不支持）
- ❌ 不要省略 front matter 中的 bridge 字段
- ❌ 不要使用过深的章节嵌套

## 示例文档

完整示例见 `data/seed/documents/` 目录。
```

**Step 2: Commit**

```bash
git add docs/ingest-guide.md
git commit -m "docs: add ingest guide"
```

---

### Task 9: 创建快速开始指南

**Files:**
- Create: `docs/getting-started.md`

**Step 1: 编写快速开始指南**

创建 `docs/getting-started.md`：

```markdown
# 快速开始

本指南帮助你在本地环境快速运行 Bridge RAG 系统。

## 环境要求

- Python 3.11+
- Docker & Docker Compose
- 智谱 AI API Key（用于 embedding 和生成）

## 安装步骤

### 1. 克隆仓库

```bash
git clone https://github.com/your-org/bridge-rag.git
cd bridge-rag
```

### 2. 启动数据库

```bash
docker compose up -d db
```

这会启动 PostgreSQL + pgvector，端口 5433。

### 3. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入 ZHIPU_API_KEY
```

### 4. 安装依赖

```bash
pip install -e ".[dev]"
```

### 5. 初始化数据库

```bash
python scripts/reset_db.py --force --seed
```

### 6. 启动服务

```bash
uvicorn app.main:app --reload
```

服务运行在 http://localhost:8000

## 验证安装

### 健康检查

```bash
curl http://localhost:8000/health
# {"status": "ok"}
```

### 测试问答

```bash
curl -X POST http://localhost:8000/api/v1/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "石拱桥的结构特点是什么？"}'
```

## 下一步

- [API 文档](api/v1.md) - 了解完整 API
- [入库指南](ingest-guide.md) - 导入自己的数据
- [架构文档](architecture.md) - 理解系统设计
```

**Step 2: Commit**

```bash
git add docs/getting-started.md
git commit -m "docs: add getting started guide"
```

---

### Task 10: 创建架构文档

**Files:**
- Create: `docs/architecture.md`

**Step 1: 编写架构文档**

创建 `docs/architecture.md`：

```markdown
# 系统架构

## 概述

Bridge RAG System 是一个面向桥梁知识的检索增强生成系统，采用三通道混合检索策略，支持精准问答和类比分析。

## 系统架构图

```
┌─────────────────────────────────────────────────────────────┐
│                        Client                                │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     FastAPI Server                           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ /api/v1/ask │  │/api/v1/ingest│  │     /health        │  │
│  └──────┬──────┘  └──────┬──────┘  └─────────────────────┘  │
└─────────┼────────────────┼──────────────────────────────────┘
          │                │
          ▼                ▼
┌─────────────────────────────────────────────────────────────┐
│                    Services Layer                            │
│  ┌────────────────┐  ┌────────────────┐  ┌───────────────┐  │
│  │ HybridRetriever│  │ MarkdownParser │  │   Generator   │  │
│  │  - Anchor      │  │                │  │               │  │
│  │  - Concept     │  │                │  │               │  │
│  │  - Analogy     │  │                │  │               │  │
│  └───────┬────────┘  └───────┬────────┘  └───────┬───────┘  │
│          │                   │                   │           │
│  ┌───────┴────────┐  ┌───────┴────────┐  ┌──────┴────────┐  │
│  │ FacetExtractor │  │    Chunker     │  │    Tagger     │  │
│  └───────┬────────┘  └───────┬────────┘  └───────┬───────┘  │
│          │                   │                   │           │
│  ┌───────┴────────┐  ┌───────┴────────┐  ┌──────┴────────┐  │
│  │   Tokenizer    │  │ContextEnricher │  │    Ranker     │  │
│  └────────────────┘  └────────────────┘  └───────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Provider Layer                            │
│  ┌─────────────────────────────────────────────────────────┐│
│  │                   ZhipuProvider                          ││
│  │  - embed(): 2048-dim vectors (embedding-3)              ││
│  │  - chat(): GLM-4 generation                             ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Data Layer                                │
│  ┌─────────────────────────────────────────────────────────┐│
│  │              PostgreSQL + pgvector                       ││
│  │  - chunks: content, embedding, tsv, taxonomy            ││
│  │  - bridges: metadata, facets                            ││
│  │  - sources: type, title                                 ││
│  │  - taxonomy_nodes: lvl1/lvl2/lvl3                       ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

## 核心模块

### 检索层

| 模块 | 职责 |
|------|------|
| HybridRetriever | 三通道混合检索：Anchor + Concept + Analogy |
| FacetExtractor | 从问题提取结构化维度（桥型、材料、年代等） |
| Ranker | RRF 融合排序 + 多样性约束 |
| Tokenizer | jieba 分词 + 自定义词典 |

### 入库层

| 模块 | 职责 |
|------|------|
| MarkdownParser | 解析 Markdown + YAML front matter |
| Chunker | 语义切块（基于 embedding 相似度） |
| ContextEnricher | 为 chunk 生成上下文描述 |
| Tagger | LLM 自动标注 taxonomy |

### 生成层

| 模块 | 职责 |
|------|------|
| Generator | 基于证据生成回答，输出置信度 |

## 数据流

### 问答流程

```
Question → Facet提取 → 三通道检索 → RRF融合 → LLM生成 → Response
              ↓              ↓
         bridge_type    Anchor: 本桥 (6条)
         material       Concept: 通用 (2条)
         era            Analogy: 类比 (2条)
         region
         function
```

### 入库流程

```
Markdown → Parse → Chunk → Enrich → Tag → Embed → Store
   ↓         ↓       ↓        ↓       ↓      ↓       ↓
 YAML    Sections  200-500  Context  lvl1  2048d   chunks
 front              chars   text    lvl2   vec    table
 matter                             lvl3
```

## 配置

- `config/taxonomy.yaml` - 三级知识分类体系
- `config/facets.yaml` - Facet 枚举值

## 技术选型

| 组件 | 技术 | 理由 |
|------|------|------|
| Web 框架 | FastAPI | 异步支持、自动 OpenAPI |
| 数据库 | PostgreSQL | 成熟稳定、pgvector 扩展 |
| 向量索引 | pgvector | 原生集成、无需额外服务 |
| LLM | 智谱 GLM-4 | 中文能力强、API 稳定 |
| Embedding | 智谱 embedding-3 | 2048 维、中文优化 |
```

**Step 2: Commit**

```bash
git add docs/architecture.md
git commit -m "docs: add architecture documentation"
```

---

### Task 11: 更新项目 README

**Files:**
- Create: `docs/README.md`

**Step 1: 编写项目 README**

创建 `docs/README.md`：

```markdown
# Bridge RAG System

桥梁知识检索增强生成系统 v1.0.0

## 特性

- **三通道混合检索** - Anchor（本桥）+ Concept（通用）+ Analogy（类比）
- **上下文增强索引** - 自动生成 chunk 上下文描述
- **Facet 智能过滤** - 按桥型、材料、年代、区域、功能过滤
- **置信度评估** - 基于证据来源评估回答可信度
- **Markdown 入库** - 支持 YAML front matter 的标准化格式

## 快速开始

```bash
# 启动数据库
docker compose up -d db

# 安装依赖
pip install -e ".[dev]"

# 初始化数据
python scripts/reset_db.py --force --seed

# 启动服务
uvicorn app.main:app --reload
```

详见 [快速开始指南](getting-started.md)

## API

| 端点 | 描述 |
|------|------|
| `GET /health` | 健康检查 |
| `POST /api/v1/ask` | 问答 |
| `POST /api/v1/ingest` | 入库 |

详见 [API 文档](api/v1.md)

## 文档

- [快速开始](getting-started.md)
- [API 参考](api/v1.md)
- [入库指南](ingest-guide.md)
- [系统架构](architecture.md)

## 开发

```bash
# 运行测试
pytest tests/ -v

# 重置数据库
python scripts/reset_db.py --force --seed
```

## 技术栈

- Python 3.11+ / FastAPI
- PostgreSQL + pgvector
- 智谱 AI (embedding-3 + GLM-4)

## License

MIT
```

**Step 2: Commit**

```bash
git add docs/README.md
git commit -m "docs: add project README"
```

---

### Task 12: 最终验证

**Step 1: 运行完整测试**

```bash
uv run pytest tests/ -v
```

Expected: All tests pass

**Step 2: 验证文档目录结构**

```bash
ls -la docs/
```

Expected:
```
docs/
├── README.md
├── getting-started.md
├── architecture.md
├── ingest-guide.md
├── api/
│   └── v1.md
└── plans/
```

**Step 3: 验证种子数据目录**

```bash
ls -la data/seed/
ls -la data/seed/documents/
```

Expected:
```
data/seed/
├── bridges.yaml
├── questions.yaml
└── documents/
    ├── 云渡桥.md
    ├── 青石关桥.md
    ├── 碧波廊桥.md
    ├── 铁索寒桥.md
    ├── 永安木桥.md
    ├── 钱塘铁桥.md
    ├── 南海风雨桥.md
    ├── 珠江悬索桥.md
    ├── 洞庭浮桥.md
    ├── 长江斜拉桥.md
    ├── 丝路古渡桥.md
    └── 冰城竹桥.md
```

**Step 4: 最终提交**

```bash
git log --oneline -10
```

---

## 任务清单

| # | 任务 | 文件 |
|---|------|------|
| 1 | 创建桥梁档案数据 | `data/seed/bridges.yaml` |
| 2 | 创建测试问题集 | `data/seed/questions.yaml` |
| 3 | 创建桥梁文档（第一批） | `data/seed/documents/*.md` (4个) |
| 4 | 创建桥梁文档（第二批） | `data/seed/documents/*.md` (4个) |
| 5 | 创建桥梁文档（第三批） | `data/seed/documents/*.md` (4个) |
| 6 | 更新种子数据脚本 | `scripts/seed_test_data.py` |
| 7 | 创建 API 文档 | `docs/api/v1.md` |
| 8 | 创建入库指南 | `docs/ingest-guide.md` |
| 9 | 创建快速开始指南 | `docs/getting-started.md` |
| 10 | 创建架构文档 | `docs/architecture.md` |
| 11 | 创建项目 README | `docs/README.md` |
| 12 | 最终验证 | - |
