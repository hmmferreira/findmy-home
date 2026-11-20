"""Public-code-only shared image probe. Never load a native artifact or session."""
import asyncio
import os
from findmy_home.shared_runtime import require_shared_backend,configure_runtime
from findmy_home.artifact_policy import reviewed_artifact,ArtifactBlocked
from findmy_home.native_worker import _NativeChannel

assert os.getuid()==1000
require_shared_backend()
assert configure_runtime({'runtime_mode':'shared'})=='shared'
try:reviewed_artifact('applemusic-arm64-v8a')
except ArtifactBlocked as error:assert error.code=='artifact_review_required'
else:raise AssertionError('Update smoke expectations after deliberate artifact approval')

async def probe():
    channel=_NativeChannel()
    try:
        async with asyncio.timeout(10):await channel._start()
    finally:await channel.close()
    assert channel._process.returncode is not None

asyncio.run(probe())
print('Shared smoke passed: pinned candidate, non-root, real native-worker boundary, default artifact refusal; no native artifact loaded.')
