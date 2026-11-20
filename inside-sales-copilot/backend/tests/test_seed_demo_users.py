import importlib.machinery
import importlib.util
import io
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

ROOT = Path(__file__).resolve().parents[2]
_loader = importlib.machinery.SourceFileLoader("seed_demo_users", str(ROOT / "scripts" / "seed-demo-users"))
_spec = importlib.util.spec_from_loader("seed_demo_users", _loader)
seed_mod = importlib.util.module_from_spec(_spec)
_loader.exec_module(seed_mod)

PASSWORD = "Demo-Passw0rd-123!"


@pytest.fixture()
def pool():
    with mock_aws():
        client = boto3.client("cognito-idp", region_name="us-east-1")
        pool_id = client.create_user_pool(
            PoolName="test", UsernameAttributes=["email"],
            Schema=[{"Name": "bu", "AttributeDataType": "String", "Mutable": True}],
        )["UserPool"]["Id"]
        yield client, pool_id


def attrs(client, pool_id, email):
    user = client.admin_get_user(UserPoolId=pool_id, Username=email)
    return {a["Name"]: a["Value"] for a in user["UserAttributes"]}, user["UserStatus"]


def test_both_demo_users_exist_with_the_right_bu_and_a_permanent_password(pool):
    client, pool_id = pool
    out = io.StringIO()
    assert seed_mod.seed(client, pool_id, PASSWORD, out=out) == ["se-aws@demo.local", "se-servicenow@demo.local"]
    a, status = attrs(client, pool_id, "se-aws@demo.local")
    assert a["custom:bu"] == "AWS" and a["email_verified"] == "true" and status == "CONFIRMED"
    a, _ = attrs(client, pool_id, "se-servicenow@demo.local")
    assert a["custom:bu"] == "ServiceNow"


def test_running_twice_causes_no_error_and_fixes_the_bu(pool):
    client, pool_id = pool
    seed_mod.seed(client, pool_id, PASSWORD, out=io.StringIO())
    client.admin_update_user_attributes(UserPoolId=pool_id, Username="se-aws@demo.local",
                                        UserAttributes=[{"Name": "custom:bu", "Value": "Salesforce"}])
    out = io.StringIO()
    seed_mod.seed(client, pool_id, PASSWORD, out=out)
    assert "se-aws@demo.local: updated" in out.getvalue()
    assert attrs(client, pool_id, "se-aws@demo.local")[0]["custom:bu"] == "AWS"


def test_the_password_is_never_printed(pool, capsys):
    client, pool_id = pool
    out = io.StringIO()
    seed_mod.seed(client, pool_id, PASSWORD, out=out)
    captured = capsys.readouterr()
    assert PASSWORD not in out.getvalue() + captured.out + captured.err


def test_main_reads_the_password_from_stdin_and_never_echoes_it(pool, monkeypatch, capsys):
    client, pool_id = pool
    monkeypatch.setattr("sys.stdin", io.StringIO(PASSWORD + "\n"))
    assert seed_mod.main(["--user-pool-id", pool_id, "--password-stdin"]) == 0
    captured = capsys.readouterr()
    assert PASSWORD not in captured.out + captured.err
    assert attrs(client, pool_id, "se-servicenow@demo.local")[1] == "CONFIRMED"


def test_mismatched_prompts_change_nothing(pool, monkeypatch):
    client, pool_id = pool
    answers = iter([PASSWORD, "something-else"])
    monkeypatch.setattr(seed_mod.getpass, "getpass", lambda prompt="": next(answers))
    assert seed_mod.main(["--user-pool-id", pool_id]) == 2
    assert client.list_users(UserPoolId=pool_id)["Users"] == []


def test_there_is_no_password_argument():
    with pytest.raises(SystemExit):
        seed_mod.main(["--password", PASSWORD])


def test_the_password_is_not_in_the_repo():
    for path in (ROOT / "scripts").iterdir():
        if path.is_file():
            assert PASSWORD not in path.read_text(encoding="utf-8", errors="ignore")
