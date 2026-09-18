import os

# 测试默认用内存外的本地 sqlite，无需 Postgres；须在导入 app.* 之前设置。
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_seatbond.db")
os.environ.setdefault("SEED_ON_EMPTY", "false")
