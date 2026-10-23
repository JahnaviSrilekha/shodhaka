from shodhaka.documents.model import Document, Section
from shodhaka.rules import checks


def doc(path, text, kind="config"):
    return Document(path, kind, text, path, [Section("s1", path, text, 1)])


def test_secret_scan_flags_literals_but_not_placeholders():
    d = doc("a.yml", "spring:\n  datasource:\n    password: hunter2\n    username: app\nx:\n  api-key: ${API_KEY}\n")
    result = checks.secret_scan(d)
    assert result.verdict == "gap"
    assert result.evidence == [{"line": 3, "text": "spring.datasource.password = <literal value redacted>"}]
    assert "hunter2" not in str(result.evidence)


def test_secret_scan_properties_line_number():
    d = doc("a.properties", "a=1\nspring.datasource.password=${vault:secret/x#p}\npsp.client.secret=pk_live_abc\n")
    result = checks.secret_scan(d)
    assert result.verdict == "gap" and result.evidence[0]["line"] == 3


def test_health_endpoint():
    ok = doc("a.yml", "spring:\n  application:\n    name: x\nmanagement:\n  endpoints:\n    web:\n      exposure:\n        include: health,info\n")
    default = doc("b.yml", "spring:\n  application:\n    name: x\n")
    narrowed = doc("d.yml", "spring:\n  application:\n    name: x\nmanagement:\n  endpoints:\n    web:\n      exposure:\n        include: info\n")
    excluded = doc("e.properties", "spring.application.name=x\nmanagement.endpoints.web.exposure.exclude=health\n")
    disabled = doc("f.properties", "spring.application.name=x\nmanagement.endpoint.health.enabled=false\n")
    assert checks.health_endpoint(ok).verdict == "compliant"
    assert checks.health_endpoint(default).verdict == "compliant"  # Spring Boot exposes health by default
    assert "by default" in checks.health_endpoint(default).note
    assert checks.health_endpoint(narrowed).verdict == "gap" and checks.health_endpoint(narrowed).evidence[0]["line"] == 8
    assert checks.health_endpoint(excluded).verdict == "gap" and checks.health_endpoint(excluded).evidence[0]["line"] == 2
    assert checks.health_endpoint(disabled).verdict == "gap"
    assert checks.health_endpoint(doc("c.yml", "foo: bar\n")).verdict == "not_applicable"


def test_pinned_base_image():
    assert checks.pinned_base_image(doc("D", "FROM eclipse-temurin:21.0.4_7-jre\n", "dockerfile")).verdict == "compliant"
    assert checks.pinned_base_image(doc("D", "FROM eclipse-temurin:latest\n", "dockerfile")).verdict == "gap"
    assert checks.pinned_base_image(doc("D", "FROM eclipse-temurin\n", "dockerfile")).verdict == "gap"
    assert checks.pinned_base_image(doc("D", "FROM registry:5000/team/img\n", "dockerfile")).verdict == "gap"
    assert checks.pinned_base_image(doc("D", "FROM img@sha256:abc AS build\nFROM scratch\n", "dockerfile")).verdict == "compliant"


def test_secret_line_follows_the_yaml_path():
    text = "spring:\n  data:\n    mongodb:\n      password: ${MONGODB_PASSWORD}\n  mail:\n    host: smtp.example.com\n    password: hunter2\n"
    result = checks.secret_scan(doc("n.yml", text))
    assert result.verdict == "gap" and result.evidence[0]["line"] == 7 and "hunter2" not in str(result.evidence)


def test_build_stages_are_not_base_images():
    text = ("FROM mcr.microsoft.com/dotnet/sdk:10.0 AS builder\nRUN make\nFROM builder AS publish\n"
            "FROM alpine:3.20 AS base\nFROM base\n")
    assert checks.pinned_base_image(doc("x.Dockerfile", text)).verdict == "compliant"
    assert checks.pinned_base_image(doc("y.Dockerfile", "FROM node AS builder\nFROM builder\n")).verdict == "gap"


def test_spring_profiles_in_one_yaml_file():
    text = ("spring:\n  application:\n    name: customers\n---\nspring:\n  config:\n    activate:\n      on-profile: docker\n"
            "  datasource:\n    password: s3cret\n")
    assert checks.health_endpoint(doc("a.yml", text)).verdict == "compliant"   # was not_applicable: only doc 1 was read
    result = checks.secret_scan(doc("a.yml", text))
    assert result.verdict == "gap" and result.evidence[0]["line"] == 10        # secret in the docker profile is found
