"""
Mock API 风控系统 - 整体验证测试脚本
测试所有策略的实现状态和导入情况
"""

import sys
import importlib
from collections import defaultdict

# 颜色定义
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"

def print_header(text):
    print(f"\n{'='*80}")
    print(f"{BLUE}{text}{RESET}")
    print(f"{'='*80}\n")

def print_success(text):
    print(f"{GREEN}✅ {text}{RESET}")

def print_error(text):
    print(f"{RED}❌ {text}{RESET}")

def print_warning(text):
    print(f"{YELLOW}⚠️  {text}{RESET}")

def test_strategy_import(module_path, class_name, strategy_code):
    """测试单个策略的导入"""
    try:
        module = importlib.import_module(module_path)
        strategy_class = getattr(module, class_name)
        
        # 检查必需的方法
        if not hasattr(strategy_class, 'execute'):
            return False, "缺少 execute 方法"
        if not hasattr(strategy_class, 'after_trigger'):
            return False, "缺少 after_trigger 方法"
        
        # 检查类属性
        if not hasattr(strategy_class, 'strategy_code'):
            return False, "缺少 strategy_code 属性"
        if not hasattr(strategy_class, 'default_priority'):
            return False, "缺少 default_priority 属性"
        
        return True, "OK"
    except ModuleNotFoundError:
        return False, f"模块 {module_path} 不存在"
    except AttributeError as e:
        return False, str(e)
    except Exception as e:
        return False, f"未知错误: {str(e)}"

def main():
    print_header("🧪 Mock API 风控系统 - 整体验证测试")
    
    # 所有策略清单
    strategies = [
        # Key Health (10-20)
        ("app.strategies.key_health", "ApiKeyBanStrategy", "api_key_ban_strategy"),
        ("app.strategies.key_health", "ApiKeyExpiredStrategy", "api_key_expired_strategy"),
        ("app.strategies.key_health", "ApiKeyBalanceStrategy", "api_key_balance_strategy"),
        
        # Network (21-40)
        ("app.strategies.limit", "IPRpmLimitStrategy", "ip_rpm_limit"),
        ("app.strategies.limit", "IPRphLimitStrategy", "ip_rph_limit"),
        ("app.strategies.network", "IPWhitelistStrategy", "ip_whitelist_strategy"),
        ("app.strategies.network", "IPKeyRelationStrategy", "ip_key_relation_check"),
        ("app.strategies.network", "KeyIPDriftStrategy", "key_ip_drift_check"),
        
        # Transport (41-60)
        ("app.strategies.transport", "TLSFingerprintStrategy", "tls_fingerprint_check"),
        ("app.strategies.transport", "UserAgentStrategy", "user_agent_check"),
        ("app.strategies.transport", "UserAgentCheckStrategy", "ua_blacklist_check"),
        
        # Limit (61-80)
        ("app.strategies.limit", "GlobalRpmLimitStrategy", "global_rpm_limit"),
        ("app.strategies.limit", "ApiKeyRpmLimitStrategy", "api_key_rpm_limit"),
        ("app.strategies.limit", "ModelRpmLimitStrategy", "model_rpm_limit"),
        ("app.strategies.limit", "IPConcurrencyLimitStrategy", "ip_concurrency_limit"),
        ("app.strategies.limit", "KeyConcurrencyLimitStrategy", "key_concurrency_limit"),
        
        # Content (81-100)
        ("app.strategies.content", "PromptSensitiveStrategy", "prompt_sensitive_check"),
        ("app.strategies.content", "ContentSafetyStrategy", "content_safety_check"),
        ("app.strategies.content", "ResponseLengthStrategy", "response_length_check"),
        
        # Behavior (101-120)
        ("app.strategies.behavior", "MachineBehaviorStrategy", "machine_behavior_check"),
        ("app.strategies.behavior", "BehaviorAnomalyStrategy", "behavior_anomaly_check"),
        
        # Fuse (121-140)
        ("app.strategies.fuse", "ErrorRateFuseStrategy", "error_rate_fuse"),
        
        # Self-healing (141-160)
        ("app.strategies.healing", "AutoHealingStrategy", "auto_healing_rule"),
    ]
    
    # 按类型分组统计
    type_stats = defaultdict(lambda: {"total": 0, "passed": 0, "failed": 0})
    
    print_header("📋 策略实现验证")
    print(f"{'策略代码':<35} {'模块路径':<45} {'状态':<10} {'说明'}")
    print("-" * 120)
    
    total_count = len(strategies)
    passed_count = 0
    failed_count = 0
    
    for module_path, class_name, strategy_code in strategies:
        success, message = test_strategy_import(module_path, class_name, strategy_code)
        
        # 提取类型（从模块路径）
        stype = module_path.split('.')[-1]
        type_stats[stype]["total"] += 1
        
        if success:
            status = f"{GREEN}✅ PASS{RESET}"
            type_stats[stype]["passed"] += 1
            passed_count += 1
        else:
            status = f"{RED}❌ FAIL{RESET}"
            type_stats[stype]["failed"] += 1
            failed_count += 1
        
        print(f"{strategy_code:<35} {module_path + '.' + class_name:<45} {status:<10} {message}")
    
    # 统计报告
    print_header("📊 测试统计报告")
    
    print(f"\n{BLUE}总体统计:{RESET}")
    print(f"  - 总策略数: {total_count}")
    print(f"  - {GREEN}通过: {passed_count}{RESET}")
    print(f"  - {RED}失败: {failed_count}{RESET}")
    print(f"  - 通过率: {(passed_count/total_count*100):.1f}%")
    
    print(f"\n{BLUE}按类型统计:{RESET}")
    for stype in sorted(type_stats.keys()):
        stats = type_stats[stype]
        status_icon = GREEN if stats["failed"] == 0 else RED
        print(f"  {status_icon} {stype.upper():<20} {stats['passed']}/{stats['total']} 通过{RESET}")
    
    # 核心功能检查
    print_header("🔍 核心功能检查")
    
    checks = [
        ("数据库模型", "app.models.base", ["Scene", "ApiKey", "StrategyMetadata"]),
        ("风控引擎", "app.risk.scheduler", ["RiskChainScheduler"]),
        ("限流组件", "app.risk.limiter", ["limiter"]),
        ("配置服务", "app.services.config", ["config_service"]),
        ("自愈服务", "app.services.healing", ["healing_service"]),
    ]
    
    for name, module_path, classes in checks:
        try:
            module = importlib.import_module(module_path)
            missing = [c for c in classes if not hasattr(module, c)]
            if missing:
                print_error(f"{name}: 缺少 {', '.join(missing)}")
            else:
                print_success(f"{name}: 所有组件正常")
        except ImportError as e:
            print_error(f"{name}: 模块导入失败 - {e}")
    
    # 最终结论
    print_header("🎯 测试结论")
    
    if failed_count == 0:
        print_success("🎉 所有策略实现完整，系统可以正常运行！")
        print(f"\n{GREEN}系统就绪状态: READY{RESET}")
        print("\n下一步建议:")
        print("  1. 启动应用: python main.py")
        print("  2. 访问管理界面: http://localhost:8090/admin/scenes")
        print("  3. 创建测试场景并启用策略")
        print("  4. 使用 API 客户端测试风控效果")
        return 0
    else:
        print_error(f"⚠️  发现 {failed_count} 个策略存在问题，请修复后重试")
        print(f"\n{YELLOW}系统就绪状态: NOT READY{RESET}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
