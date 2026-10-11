# 数据接口字典与固定验收

`handoff_schema.json`、`field_dictionary.csv`、`source_map.csv`、`codebook.json`和`policy_snapshot.json`定义完整接口模板，包含默认OFF字段。实际交接只使用正式包自己的已启用schema和字典，不能要求模板的OFF文件存在。

`assertion_index.json`保留53个P05、68个H05原ID与原用例内容。2026-10-12清理后，当前来源指向定版合同；被删除的候选稿路径及SHA保存在每项`historical_provenance`，仅用于历史来源说明。这个指针修改不改变断言或解析规则。

`tests/fixtures/v12_baseline.json`显式R4只更新两个合同的阶段说明/链接及索引来源，完整R3哈希保存为`prior_binding`。配置、实现、测试和旧H04固定绑定保持原字节；运行器不自动重绑。当前状态见[正式验收摘要](../DATA_HANDOFF_ACCEPTANCE.md)。
