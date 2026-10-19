# Third-party attribution

The API catalog in `src/yicloud/data/catalog.json` is generated from the public
Yicloud Go SDK v0.5.1, commit 8f8d27e2b466b7ceac5dacfa12900d03ad70e3d5:
https://gitee.com/yicloud-team/openapi-sdk-go

Its field descriptions, schemas, constants and operation descriptions are derived
from that SDK. Those derived portions remain under Apache License 2.0, reproduced
in `licenses/Yicloud-SDK-Apache-2.0.txt`. The upstream checkout contains no NOTICE
file. The Python transport/signature implementation is independently written
against the SDK contract; `tools/sign_vectors.go` calls the unmodified upstream
algorithm to generate interoperability test vectors. The Go SDK is not a runtime
dependency.

The CLI + Skill architecture and optional stable asset document are inspired by
InspireSkill (MIT), https://github.com/realZillionX/InspireSkill. No InspireSkill
source code or account data is included.

Yicloud product names belong to their respective owners. This community project
is not an official Yicloud SDK. All test payloads are synthetic and do not prove
live platform compatibility.
