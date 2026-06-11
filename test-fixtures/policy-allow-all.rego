package ods.policy

# Allow-all policy for testing
default allow := true

warn[msg] {
    input.ai_generated == true
    msg = "AI code detected — review recommended"
}
