"""Operational verification example for Kompressor."""

from kompressor.legacy import ClaudeTokenSaver

mock_log_payload = [
    {"id": "AX-912", "event": "auth_timeout_error", "ip": "10.0.1.250", "severity": "CRITICAL"},
    {"id": "AX-913", "event": "db_query_slow_exec", "ip": "10.0.4.12", "severity": "WARNING"},
    {"id": "AX-914", "event": "api_gateway_success", "ip": "192.168.1.5", "severity": "INFO"},
] * 200

analysis = ClaudeTokenSaver().calculate_savings(mock_log_payload)

print("=== CLAUDE CONTEXT SAVINGS METRICS ===")
print(f"Standard Payload Footprint:  {analysis['standard_tokens']:,} tokens")
print(f"Optimized Payload Footprint: {analysis['optimized_tokens']:,} tokens")
print(f"Total Efficiency Gain:       {analysis['percent_saved']}% fewer estimated tokens")
print(f"Direct API Cost Reduction:   ${analysis['financial_saved_per_run']:.6f} estimated saved per batch")
