"""
策略实现状态检查报告
生成时间: 2026-05-04
"""

import os
import importlib

# 已注册的策略列表（从数据库查询结果）
registered_strategies = [
    # Key Health (10-20)
    {"code": "api_key_expired_strategy", "handler": "app.strategies.key_health.ApiKeyExpiredStrategy", "type": "key_health"},
    {"code": "api_key_balance_strategy", "handler": "app.strategies.key_health.ApiKeyBalanceStrategy", "type": "key_health"},
    
    # Network (21-40)
    {"code": "ip_rpm_limit", "handler": "app.strategies.limit.IPRpmLimitStrategy", "type": "network"},
    {"code": "ip_rph_limit", "handler": "app.strategies.limit.IPRphLimitStrategy", "type": "network"},
    {"code": "ip_whitelist_strategy", "handler": "app.strategies.network.IPWhitelistStrategy", "type": "network"},
    {"code": "ip_key_relation_check", "handler": "app.strategies.network.IPKeyRelationStrategy", "type": "network"},
    {"code": "key_ip_drift_check", "handler": "app.strategies.network.KeyIPDriftStrategy", "type": "network"},
    
    # Transport (41-60)
    {"code": "tls_fingerprint_check", "handler": "app.strategies.transport.TLSFingerprintStrategy", "type": "transport"},
    {"code": "user_agent_check", "handler": "app.strategies.transport.UserAgentStrategy", "type": "transport"},
    {"code": "ua_blacklist_check", "handler": "app.strategies.transport.UserAgentCheckStrategy", "type": "transport"},
    
    # Limit (61-80)
    {"code": "global_rpm_limit", "handler": "app.strategies.limit.GlobalRpmLimitStrategy", "type": "limit"},
    {"code": "api_key_rpm_limit", "handler": "app.strategies.limit.ApiKeyRpmLimitStrategy", "type": "limit"},
    {"code": "model_rpm_limit", "handler": "app.strategies.limit.ModelRpmLimitStrategy", "type": "limit"},
    {"code": "ip_concurrency_limit", "handler": "app.strategies.limit.IPConcurrencyLimitStrategy", "type": "limit"},
    {"code": "key_concurrency_limit", "handler": "app.strategies.limit.KeyConcurrencyLimitStrategy", "type": "limit"},
    
    # Content (81-100)
    {"code": "prompt_sensitive_check", "handler": "app.strategies.content.PromptSensitiveStrategy", "type": "content"},
    {"code": "response_length_check", "handler": "app.strategies.content.ResponseLengthStrategy", "type": "content"},
    {"code": "content_safety_check", "handler": "app.strategies.content.ContentSafetyStrategy", "type": "content"},
    
    # Behavior (101-120)
    {"code": "behavior_anomaly_check", "handler": "app.strategies.behavior.BehaviorAnomalyStrategy", "type": "behavior"},
    {"code": "machine_behavior_check", "handler": "app.strategies.behavior.MachineBehaviorStrategy", "type": "behavior"},
    
    # Fuse (121-140)
    {"code": "error_rate_fuse", "handler": "app.strategies.fuse.ErrorRateFuseStrategy", "type": "fuse"},
    
    # Self-healing (141-160)
    {"code": "auto_healing_rule", "handler": "app.strategies.healing.AutoHealingStrategy", "type": "self_healing"},
]

def check_strategy_implementation(strategy):
    """检查策略实现是否完整"""
    handler_path = strategy["handler"]
    parts = handler_path.rsplit(".", 1)  # 从右边分割一次
    
    if len(parts) != 2:
        return {"status": "ERROR", "reason": f"Invalid handler path: {handler_path}"}
    
    module_path = parts[0]
    class_name = parts[1]
    
    try:
        # 尝试导入模块
        module = importlib.import_module(module_path)
        
        # 检查类是否存在
        if not hasattr(module, class_name):
            return {"status": "MISSING_CLASS", "reason": f"Class {class_name} not found in {module_path}"}
        
        # 获取类
        strategy_class = getattr(module, class_name)
        
        # 检查是否有 execute 方法
        if not hasattr(strategy_class, "execute"):
            return {"status": "MISSING_EXECUTE", "reason": f"Class {class_name} missing execute method"}
        
        # 检查是否有 after_trigger 方法
        if not hasattr(strategy_class, "after_trigger"):
            return {"status": "MISSING_AFTER_TRIGGER", "reason": f"Class {class_name} missing after_trigger method"}
        
        return {"status": "OK", "reason": "Implementation complete"}
        
    except ModuleNotFoundError:
        return {"status": "MISSING_MODULE", "reason": f"Module {module_path} not found"}
    except Exception as e:
        return {"status": "ERROR", "reason": str(e)}

def main():
    print("=" * 120)
    print("策略实现状态检查报告")
    print("=" * 120)
    print()
    
    # 按类型分组
    strategies_by_type = {}
    for s in registered_strategies:
        stype = s["type"]
        if stype not in strategies_by_type:
            strategies_by_type[stype] = []
        strategies_by_type[stype].append(s)
    
    total_ok = 0
    total_issues = 0
    
    for stype in sorted(strategies_by_type.keys()):
        strategies = strategies_by_type[stype]
        print(f"\n{'='*120}")
        print(f"策略类型: {stype.upper()} ({len(strategies)} 个策略)")
        print(f"{'='*120}")
        print(f"{'策略代码':<35} {'处理器路径':<60} {'状态':<15} {'说明'}")
        print(f"{'-'*35} {'-'*60} {'-'*15} {'-'*40}")
        
        for s in strategies:
            result = check_strategy_implementation(s)
            
            if result["status"] == "OK":
                status_icon = "✅ 正常"
                total_ok += 1
            else:
                status_icon = "❌ 异常"
                total_issues += 1
            
            print(f"{s['code']:<35} {s['handler']:<60} {status_icon:<15} {result['reason']}")
    
    print(f"\n{'='*120}")
    print(f"总结:")
    print(f"  - 总计策略数: {len(registered_strategies)}")
    print(f"  - 实现正常: {total_ok}")
    print(f"  - 存在问题: {total_issues}")
    print(f"{'='*120}")

if __name__ == "__main__":
    main()
