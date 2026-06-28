# Fixture for the self-test Semgrep rule (test-fixtures/semgrep-rules.yml).
# The eval() below is intentionally flagged by ods-test-eval-call.
def run(user_input):
    return eval(user_input)
