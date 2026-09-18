import os

# 必须在导入任何 app 模块之前生效：config 在 import 时读取环境变量。
# 测试使用共享内存 SQLite（database.py 已为其启用 StaticPool），并关闭种子数据。
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SEED_ON_EMPTY"] = "false"
