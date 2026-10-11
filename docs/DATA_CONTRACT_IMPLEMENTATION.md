# 数据合同实现与测试基线

政策v1.2、业务基底v1.1的解析、构造、读回和消费者路径已实现，正式真实数据也已完成验收。当前正式状态见[DATA_HANDOFF_ACCEPTANCE.md](DATA_HANDOFF_ACCEPTANCE.md)，接收方入口见[MODELING_HANDOFF.md](MODELING_HANDOFF.md)。

实现位于[src/steam_parse.py](../src/steam_parse.py)和[src/steam_handoff.py](../src/steam_handoff.py)。解析保留字面原值、缺失类别和序列态；交接保留全部源身份，非法键、特征及基础人口ratings阻断。标签从完整年度人口计算，历史来源独立双向重建；失败保留诊断且不生成READY。

## 验收入口

```bash
python -B -m scripts.run_data_contract_tests
```

验收仅使用合成数据，不制作正式包、不训练模型。完整制作测试记录真实Git HEAD，因此须在Git克隆仓库运行；私下ZIP的只读数据消费不依赖Git。旧H04四个绑定文件原SHA不变，以[冻结v1.1配置](../tests/fixtures/legacy_v11/config.py)在临时副本执行11项。当前[固定v1.2基线](../tests/fixtures/v12_baseline.json)绑定15项实现、测试和合同文件；文件缺失或hash变化阻断，运行器不自动刷新基线。

53条P05和68条H05在实际断言后逐条记录，静态索引与历史提案不替代执行结果。直接把旧H04测试运行于当前v1.2配置仍会触发原SHA守卫；应使用上述统一入口。

## 已验证的实现修订

| 基线修订 | 已验证结果与边界 |
|---|---|
| R1/R2，2026-10-11 | 合同实现合成验收完成。R2旧H04 11/11、当前148/148，包含53P05、68H05、5业务回归及22补充回归；正式目录限制修复显式更新两个绑定。 |
| R3，2026-10-11 | 真实制作必要修复SteamSpy原生appid列适配及完整历史重建性能，显式更新3个绑定，其他12项和旧H04不变。旧H04 11/11、当前150/150：53P05、68H05、5业务回归和24补充回归，零失败、错误或跳过。正式real-file验收及独立消费者随后通过。 |
| R4，2026-10-12 | 本次目录规整修正两个仓库合同的当前状态和断链引用，以及assertion_index的来源/状态说明，显式记录三个新文档hash；基线保留R3 prior_binding及三文件旧hash。config、实现、测试和封存21文件不变，业务和接口语义不变；本轮实际复跑旧H04 11/11、当前150/150通过，零失败、错误或跳过。 |

此前合成证据与真实证据保持不同scope。近Int64切点比较、正式消费者虚拟READY拒绝、H05断言ID及规范键源身份缺口已有回归；真实交接成立依据为real-file报告、物理READY和包外消费者证据。

本地必要验收JSON及整理核验保留于`data/processed/acceptance/`，随私下交接包提供。目录迁移保持封存当次合同和全部21文件原字节；仓库后续文档修正不能替换封存合同或回写封存报告。旧协作过程和重复输出按2026-10-12授权清理，当前标准仍由[config.py](../config.py)及[DECISIONS.md](DECISIONS.md)定义。
