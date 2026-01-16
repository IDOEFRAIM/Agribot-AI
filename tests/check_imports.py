
try:
    from orchestrator.report_flow import DailyReportFlow
    print("Import successful")
except ImportError as e:
    print(f"Import failed: {e}")
except Exception as e:
    print(f"Other error: {e}")
