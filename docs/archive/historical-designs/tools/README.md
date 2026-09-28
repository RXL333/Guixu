# 设计包校验工具

`validate_blueprint.py`仅验证这个设计包中的JSON、Schema、模板、参考SQL、OpenAPI引用、文档链接和已保存的静态页面尺寸检查结果。它不是应用测试，不操作个人文件，不调用模型、不联网。

在独立虚拟环境安装`jsonschema`后，从项目根运行：

```text
python tools/validate_blueprint.py
```

输出到`reports/validation-results.json`。脚本通过不表示文件执行器、真实模型、安装包或Windows句柄逻辑已经实现。OpenAPI检查为本地引用/路由/鉴权/幂等与结构一致性检查，不宣称已通过第三方完整OpenAPI规范认证。

静态页面截图由本次设计环境的系统Chromium渲染，自包含HTML以set_content载入；它证明静态布局可渲染，不证明pywebview桌面桥或file://入口行为。实施时还需执行docs/09_TESTING.md的完整测试。
