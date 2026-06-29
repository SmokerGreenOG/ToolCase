from apk_reverse_suite.core.engine import analyze_apk

result = analyze_apk(
    apk_path="example.apk",
    output_dir="reports/example",
    use_jadx=False,
    use_apktool=False,
)

print(result["summary"])
print("JSON:", result["artifacts"]["json_report"])
print("HTML:", result["artifacts"]["html_report"])
