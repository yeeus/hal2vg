# 对完整 hal2vg 输出作原版/低内存对照

比较同一个 HAL、相同 references、相同 ignore/target 参数的两个原始 PackedGraph
输出，唯一算法开关差别是 `--lowMemory`。不要拿原始输出与后续 clip/filter 图比较。
若原版完整 VG 已保留，直接使用它，不必重跑 alignment 或原版转换。

## 什么才算一致

文件大小、节点数、文件 SHA256 不要求相同：节点编号与无分支的线性切分边界可以变化。
只比较所有路径的 FASTA 也不够，因为共享节点错误地变成私有节点仍能保留相同序列。

`hal2vg-fingerprint` 和比较脚本检查：

1. 全部路径名称、长度、元数据、环状属性和完整序列，包括大小写。
2. 全部路径位置的碱基级同源共享关系及方向，包括重复拷贝与反向路径。
3. 每个路径相邻节点之间确实有边，且全部节点和边均被路径使用。

第2项将每个同源碱基锚定到按路径名排序后的首次出现位置，再合并连续区间、计算
SHA256；不依赖节点编号。第3项保证没有不被路径遍历的额外结构逃过第2项检查。
因此，PASS 是全量路径及带方向的碱基图等价的强内容校验证据，允许等价的线性切分。
它验证两个输出之间的等价性；不能单独证明两者共有的 HAL 解释错误不存在。

## 只更新验证工具，不改正在运行的转换程序

在现有且已编译成功的 hal2vg 仓库内：

```bash
git fetch origin master
git checkout origin/master -- verification.mk \
    tests/fingerprint_graph.cpp tests/compare_graph_fingerprints.py
make -f Makefile -f verification.mk hal2vg-fingerprint
```

这条编译命令只构建独立验证程序，复用现有依赖和本地 Makefile，不重编译 hal2vg。
需要 OpenSSL 的头文件及 libcrypto（例如已有环境中的 openssl-devel/libssl-dev）。
若缺少该依赖，编译会明确报错；不要为此覆盖原有 Makefile 或重新 clone。
工具只支持这个仓库使用的 PackedGraph 序列化格式，不支持 HashGraph、ODGI 或 GBZ。

## 完整 chr21 的执行命令

在有足够内存的计算节点运行，两个图按顺序检查。修改下面的目录和输入文件名。
不要在登录节点执行，也不要把两条 fingerprint 命令放到后台同时运行。

```bash
#!/usr/bin/env bash
set -eo pipefail
cd /path/to/chr21
# 如需激活原构建环境，先运行 source ./cactus.config.sh
REPO=/path/to/hal2vg-memory-step1
OLD=./hal2vg_step1/close.vg
NEW=./hal2vg_low_memory/chr21.vg
export OMP_NUM_THREADS=1
mkdir -p ./hal2vg_verify

/usr/bin/time -v -o ./hal2vg_verify/old.time.log \
    "$REPO/hal2vg-fingerprint" "$OLD" \
    > ./hal2vg_verify/old.jsonl 2> ./hal2vg_verify/old.log

/usr/bin/time -v -o ./hal2vg_verify/new.time.log \
    "$REPO/hal2vg-fingerprint" "$NEW" \
    > ./hal2vg_verify/new.jsonl 2> ./hal2vg_verify/new.log

python3 "$REPO/tests/compare_graph_fingerprints.py" \
    ./hal2vg_verify/old.jsonl ./hal2vg_verify/new.jsonl
```

先确认两次转换本身都退出成功；不要在输出仍写入时验证。`set -e` 使任何失败立即停止。
每份清单只有在完整扫描成功后才写最后的完成记录；缺失完成记录的清单会被比较脚本拒绝。

通过时输出类似：

```text
PASS: 1319 paths; ... path bases
Identical metadata, case-sensitive sequences and oriented base-level homology maps.
All nodes/edges are used by paths, and every path transition has an edge.
Node counts (diagnostic only): ... / ...
```

上面的路径数只是示例，以实际导出的路径清单为准；不把1319设为程序硬编码。
失败会列出路径和差异类型，退出码为1。保留两份清单及日志，再定位具体问题；不要忽略失败。
发现未被路径使用的节点或边时也会拒绝完成校验。这是原始 hal2vg 输出的适用条件，
不表示含有此类结构的其他来源图必然损坏。

## 资源开销和验证范围

- 每次只加载一份输出 PackedGraph，另外保存节点级锚点、短序列缓存和边覆盖标记。
  不建立逐碱基图对象，不输出整图 JSON/FASTA，也不生成庞大的临时路径文件。
- 仍需容纳输出图和辅助索引；不是几GB内存即可运行的流式解析器。
  完整 chr21 的加载峰值和耗时尚待集群实测，使用 GNU time 日志记录。
- 顺序扫描两次全部路径并计算摘要，全量验证需要额外 CPU 时间；不能将它视为瞬间完成的检查。
- PASS 不要求二进制文件相同。正式采用前，后续规范化和 VCF 流程仍应使用相同参数作对照；
  节点 ID、记录顺序和等价变异表示可能变化，不能直接用 VCF 文件哈希作结论。

## 验证工具自身的回归测试

```bash
git checkout origin/master -- tests/fingerprint_fixture.cpp tests/test_graph_fingerprints.py
make -f Makefile -f verification.mk test-graph-fingerprints
```

测试覆盖线性切分、稀疏重编号和节点翻转、环状路径、自环、折返连接、空路径；
故意破坏序列、共享关系、同源方向、路径边，添加孤立节点/多余边，或截断清单时必须失败。
生成器和测试只在小图上运行。

2026-10-25 本地 Linux 验证：12项验证器回归测试通过；20组小型 HAL 的完整
PackedGraph 新旧对照通过（HashGraph 不在本工具支持范围内）；257条路径、
5,140,000个路径碱基的合成图对照通过。完整人类 chr21 尚待集群执行。
