# 独立按文档复现记录

日期：2026-10-20。
验证方式：按 README 在新建的隔离 Python 环境中执行。
环境：同一机器上新建 `capsule_env01`，Python 3.9.6；未安装 pip/第三方依赖，未继承 site-packages。
环境探测确认 NumPy、PyYAML 不存在。

| 原样文档命令 | 退出码 | 用时 | 输出 |
| --- | --- | --- | --- |
| python3 audit_examples.py audit --out result.json | 0 | 0.30 秒 | AUDIT 3 cases; expected labels not read |
| python3 audit_examples.py check --out result.json | 0 | 0.19 秒 | CHECK PASS 3 cases; independent reference and frozen expected sets agree |

验证对象是三个历史、预计算候选表面上的诊断组件。候选前向计算没有在 capsule 中重跑；
结果不能扩展为模型 adapter、ontology evaluator 或自动 patch executor 的全流程可移植性。
MANIFEST.json 保留构建时清单；本记录与 result.json 为构建后产生的验证产物。
