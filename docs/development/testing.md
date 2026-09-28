# 测试

```powershell
python .\scripts\verify.py all
uv --directory .\backend run --all-extras pytest -q
```

测试只使用 pytest 临时目录或 `artifacts/test-workspaces`；不要指向个人文件夹。许可样本在 `backend/tests/fixtures/evaluation/`，可由 `python .\scripts\create_acceptance_samples.py` 重建。发布评测结果生成后不得为提高指标修改 gold manifest。

数据库运行时版本见 `backend/src/guixu/infrastructure/db/database.py`；当前为 11。迁移前先备份并验证数据库，失败时阻止文件操作。
