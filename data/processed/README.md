# 正式数据与验收证据

`steam_handoff_v12/`保存已通过真实文件验收的21个封存文件，保持原字节；`acceptance/`保存最终独立消费者、测试、EDA和整理核验记录。正式数据不提交GitHub，完整文件由微信交接ZIP提供。

先读[建模指南](../../docs/MODELING_HANDOFF.md)，运行`python -B -m scripts.load_modeling_data`核验。主X/y/态/切分元数据按appid关联；不要使用旧STEP1标签或切分，也不要直接把整个标签/元数据表拼入X。
