# 项目级配置覆盖示例
#
# 用法：把本文件复制到你的项目根目录，路径为 .claude/plan-test.config.md
# 只需写你要改的键；未写的沿用插件默认（见 skills/plan-test/config.md）。

# 本项目没装 codex 插件，执行阶段统一用 Claude 子代理
EXECUTOR_ENGINE: claude

# plan 至少迭代 5 轮（仍受收敛判据与 MAX_ROUNDS 约束）
PLAN_ITERATIONS: 5

# 纯后端服务，没有 UI —— 测试走脚本而非真人点击
# （TEST_STRATEGY=route 时会自动判定，这里显式声明更稳）
MANUAL_TEST: optional
TEST_STRATEGY: route

# 把循环硬上限放宽到 8
MAX_ROUNDS: 8
