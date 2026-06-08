from main import wait_before_success_exit


def test_wait_before_success_exit_waits_ten_seconds_by_default():
    calls = []

    wait_before_success_exit(sleeper=calls.append)

    assert calls == [10]
