# 低内存转换：更新、验证与运行

必须加 `--lowMemory` 才启用新模式；默认模式保留为对照。完整 chr21 尚未在本地测试，500GB 是待验证的目标，不是已测结果。

## 改变的逻辑

原流程先把碱基差异展开成大量 pinch segments，再转换成 PackedGraph。chr21 的测量中，这些 segments 约占853 GiB。

新模式保留初始 pinch 图，用每个成员每个分组区间1–8 bit的标签及共享节点区间描述碱基分组，直接生成输出图，不建立190亿个展开后的链表对象。

- 相邻区间中成员集合相同的组继续使用同一个虚拟节点，包括只有一个成员的区间。
- DNA 按窗口读取，默认总窗口预算64 MiB；反向成员按反向坐标读取并反向互补，分组状态跨窗口保留。
- 计划生成后关闭整批 HAL genome；构图时只重新打开当前 genome，并读取当前序列，避免每个输出片段都建立 HAL DNA 迭代器。
- 不写临时路径记录，不做磁盘排序。可能增加一次 HAL 输入读取，但不引入数百GB的路径暂存文件。
- 分组表、初始图和输出图仍随输入增长。`--lowMemoryBuffer` 仅控制 DNA 窗口，不是进程 RSS 上限。

原始 block 之间可能保留额外的线性节点边界，节点编号也可能变化。验证比较路径元数据、序列、碱基级同源分组和带方向的边，不要求二进制文件相同。后续 Cactus 全图规范化及 VCF 仍应在正式采用前验证。

## 更新已有目录

不用重新 clone，不更新 submodule。在上次编译成功的环境中：

```bash
# 在现有 hal2vg-memory-step1 仓库目录内执行
git fetch origin master
git checkout origin/master -- hal2vg.cpp low_memory_plan.hpp
make -j 16 hal2vg
```

运行必需更新这两个文件，依赖继续复用。本次源文件也会更新，因此现有 Makefile 会触发重新编译，不必覆盖本地 Makefile。以后若只更新头文件，先 `touch hal2vg.cpp` 再编译。

## 没有小型 HAL 时，自动生成测试数据

```bash
git checkout origin/master -- tests/low_memory_regression.py \
    tests/make_hal_subset.py tests/benchmark_low_memory.py
python3 tests/low_memory_regression.py
```

脚本自动生成小型 HAL，不需要先提取数据，默认执行20组原版/低内存对照，覆盖：

- SNP、插入缺失、N、软屏蔽大小写、倒位、重复拷贝和跨 block 重排；
- 祖先排除、指定 targets、单个 target、reference 路径及 `.1/.2` 分相命名；
- PackedGraph、HashGraph、节点切分；
- 用17字节的小窗口强制测试跨窗口状态及反向坐标。

需要 `vg` 和 Python 3。HAL 导入、改名工具使用现有 `deps/hal/bin`。Fixtures、日志及两种输出保存在 `low_memory_test/`。

检查将小图转成与节点编号及线性切分无关的碱基级表示，比较完整路径、元数据、同源成员集合及方向边。不要把这套逐碱基比较用于完整染色体。

### 本地验证记录

Linux/GCC 14.2、HAL固定依赖和 vg 1.76.0：完整程序编译通过，原有 small.t 的7项测试通过。20组自动测试及1个通过区域提取流程生成的小 HAL 对照通过。

独立合成测试：256条20 kb haplotypes，加1条reference，每条haplotype约10%替换，全部257条输出路径序列一致：

| 模式 | 最大 RSS | 运行时间 |
|---|---:|---:|
| 原转换 | 419,524 KiB（409.7 MiB） | 4.47 s |
| `--lowMemory` | 188,572 KiB（184.2 MiB） | 2.91 s |

合成样本峰值降低55.1%。这证明了中间对象减少能产生实际收益，不是完整 chr21/chr2 的资源预测。重复测试：

```bash
python3 tests/benchmark_low_memory.py
```

## 可选：从 chr21 制作真实区域子集

```bash
python3 tests/make_hal_subset.py \
    /path/to/chr21/align/chr21.hal \
    ./chr21_mini --start 20000000 --length 100000
python3 tests/low_memory_regression.py --hal ./chr21_mini/mini.hal \
    --work-dir ./chr21_mini_check
```

默认选择 GRCh38、CHM13v2、CN1v1，读取 GRCh38 的第一条序列。`--ref-sequence` 可指定序列名；`--targets` 可换成其他逗号分隔的 genome 名称。

脚本从原 HAL 导出指定参考区间的 MAF，再对每条序列重设坐标和长度，最后导入 `mini.hal`。这避免只导出100 kb，却因原染色体长度保留大量填充区域。

这是供原版和新版共同测试的区域 MAF 往返产物，不是原始 HAL 的无损裁切：未导出的比对、原始树结构及区间外信息不保留。它不用于正式图或 VCF；正式运行继续使用完整 HAL。

## 完整 chr21 测试

先完成小型测试，再在已有足够内存的计算节点作业中运行。不加 `--chop 32`，保持 Cactus 原导出参数。

```bash
#!/usr/bin/env bash
set -eo pipefail
cd /path/to/chr21
source ./cactus.config.sh
export OMP_NUM_THREADS=1
HAL2VG=/path/to/hal2vg-memory-step1/hal2vg
mkdir -p ./hal2vg_low_memory
/usr/bin/time -v -o ./hal2vg_low_memory/chr21.time.log \
    "$HAL2VG" ./align/chr21.hal \
    --lowMemory --progress --inMemory \
    --ignoreGenomes Anc0 \
    --refGenomes _MINIGRAPH_,GRCh38,CHM13v2,CN1v1 \
    > ./hal2vg_low_memory/chr21.vg \
    2> ./hal2vg_low_memory/chr21.log
grep -E '\[hal2vg-(memory|pinch|low-memory)\]' ./hal2vg_low_memory/chr21.log
```

`label_bytes` 为压缩标签长度；`plan_storage_bytes` 估算计划中各 vector 的容量，不包括分配器元数据和 map 桶。`path_spool_bytes=0` 表示不写路径暂存文件。

重点看 `after_low_memory_planning`、`after_low_memory_hal_release`、`after_graph_conversion` 及 GNU time 的最大 RSS。完成图有效性、路径和下游验证后，再用于 chr2/chr1。

## 外部证据

- [外部搜索：原 split 实现](https://github.com/yeeus/hal2vg/blob/bab3a85faeb6cf35b25bc898b7deea95d6572ee3/hal2vg.cpp#L773-L878)：碱基分组和重新 pinching。
- [外部搜索：原路径生成](https://github.com/yeeus/hal2vg/blob/bab3a85faeb6cf35b25bc898b7deea95d6572ee3/hal2vg.cpp#L904-L1094)：命名、方向和序列校验。

验证日期：2026-10-25。上述性能数字来自合成测试；完整人类染色体待集群验证。
