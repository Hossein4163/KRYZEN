# Model test — 2026-10-24 02:06

## NVIDIA NIM — 15/62 working, 12 with tool calling

| Model | Works | Tools | Latency | Reply / error |
|---|---|---|---|---|
| `nvidia/nemotron-3.5-bolt-e4b` | ✅ | ✅ | 0.5s | OK |
| `google/diffusiongemma-26b-a4b-it` | ✅ | ✅ | 0.7s |  |
| `meta/muse-glimmer-30b` | ✅ | ✅ | 0.8s |  |
| `minimaxai/minimax-m3.1-flash` | ✅ | ✅ | 1.0s | OK |
| `nvidia/nemotron-3.5-super-vl-120b-a12b` | ✅ | ✅ | 1.0s | OK |
| `nvidia/nemotron-3.5-lightning-30b-a3b` | ✅ | ✅ | 1.2s |  |
| `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` | ✅ | ✅ | 1.6s | OK |
| `stepfun-ai/step-5-preview` | ✅ | ✅ | 1.8s | OK |
| `nvidia/nemotron-3-ultra-550b-a55b` | ✅ | ✅ | 2.5s | OK |
| `poolside/laguna-xs-2.1` | ✅ | ✅ | 5.7s | OK |
| `z-ai/glm-5.3` | ✅ | ✅ | 38.2s | OK |
| `z-ai/glm-5.3-flash` | ✅ | ✅ | 42.4s |  |
| `nvidia/riva-translate-4b-instruct-v2` | ✅ | — | 0.7s | Reply with exactly: OK |
| `nvidia/ising-calibration-1.5-31b` | ✅ | — | 6.8s | I'm NVIDIA Ising-Calibration-1.5, NVIDIA |
| `meta/llama-3.2-11b-vision-instruct` | ✅ | — | 57.9s | OK |
| `01-ai/yi-large` | ❌ | — |  | HTTP 404: {"status":404,"title":"Not Found","detail":"Function '23bd454d-b225-49a3-8118-582a62fc51b8': Not found for account 'oYBM |
| `ai21labs/jamba-1.5-large-instruct` | ❌ | — |  | HTTP 404: {"status":404,"title":"Not Found","detail":"Function '6497fc2b-7ff8-4019-8946-123dccbfc863': Not found for account 'oYBM |
| `aisingapore/sea-lion-7b-instruct` | ❌ | — |  | HTTP 404: {"status":404,"title":"Not Found","detail":"Function '02f84bf4-c1a1-489b-a9de-ac3e8dcdec14': Not found for account 'oYBM |
| `bigcode/starcoder2-15b` | ❌ | — |  | HTTP 404: 404 page not found  |
| `databricks/dbrx-instruct` | ❌ | — |  | HTTP 404: {"status":404,"title":"Not Found","detail":"Function '3d6c2ff8-8bfc-4d10-8fd0-b7337288e869': Not found for account 'oYBM |
| `deepseek-ai/deepseek-coder-6.7b-instruct` | ❌ | — |  | HTTP 404: {"status":404,"title":"Not Found","detail":"Function 'e503b15c-62b0-4d69-b532-a88f0bfa2656': Not found for account 'oYBM |
| `deepseek-ai/deepseek-v4.1-flash` | ❌ | — |  | HTTP 0: TimeoutError: The read operation timed out |
| `google/codegemma-1.1-7b` | ❌ | — |  | HTTP 404: {"status":404,"title":"Not Found","detail":"Function 'e2d298c5-204e-4213-b921-9f492cc9011b': Not found for account 'oYBM |
| `google/codegemma-7b` | ❌ | — |  | HTTP 404: {"status":404,"title":"Not Found","detail":"Function '7dfc10a8-3cc4-448e-97c1-2213308dc222': Not found for account 'oYBM |
| `google/gemma-2b` | ❌ | — |  | HTTP 404: {"status":404,"title":"Not Found","detail":"Function '04174188-f742-4069-9e72-d77c2b77d3cb': Not found for account 'oYBM |
| `google/gemma-3-12b-it` | ❌ | — |  | HTTP 404: {"status":404,"title":"Not Found","detail":"Function 'ee47df99-c92b-4dc9-b3a7-f3fb0f087b73': Not found for account 'oYBM |
| `google/gemma-3-4b-it` | ❌ | — |  | HTTP 404: {"status":404,"title":"Not Found","detail":"Function 'c322f327-55a3-4af3-a91f-c757e2b8b135': Not found for account 'oYBM |
| `google/gemma-4-31b-it` | ❌ | — |  | HTTP 0: TimeoutError: The read operation timed out |
| `google/recurrentgemma-2b` | ❌ | — |  | HTTP 404: {"status":404,"title":"Not Found","detail":"Function '2f495340-a99f-4b4b-89bd-1beb003dd896': Not found for account 'oYBM |
| `ibm/granite-3.0-3b-a800m-instruct` | ❌ | — |  | HTTP 404: {"status":404,"title":"Not Found","detail":"Function '67324577-3f91-4aa6-b750-97468262530d': Not found for account 'oYBM |
| `ibm/granite-3.0-8b-instruct` | ❌ | — |  | HTTP 404: {"status":404,"title":"Not Found","detail":"Function '5a24a4f0-2d59-46b3-ac65-42307f2633d1': Not found for account 'oYBM |
| `ibm/granite-34b-code-instruct` | ❌ | — |  | HTTP 404: {"status":404,"title":"Not Found","detail":"Function '4df48b4f-e3c5-4ade-82c7-c06b65e25d18': Not found for account 'oYBM |
| `ibm/granite-8b-code-instruct` | ❌ | — |  | HTTP 404: {"status":404,"title":"Not Found","detail":"Function 'af7b6f03-f615-4c5f-86c6-388bd35cede0': Not found for account 'oYBM |
| `meta/codellama-70b` | ❌ | — |  | HTTP 404: {"status":404,"title":"Not Found","detail":"Function 'f6b06895-d073-4714-8bb2-26c09e9f6597': Not found for account 'oYBM |
| `meta/llama-3.2-90b-vision-instruct` | ❌ | — |  | HTTP 0: TimeoutError: The read operation timed out |
| `meta/llama2-70b` | ❌ | — |  | HTTP 404: {"status":404,"title":"Not Found","detail":"Function '2fddadfb-7e76-4c8a-9b82-f7d3fab94471': Not found for account 'oYBM |
| `microsoft/phi-3-vision-128k-instruct` | ❌ | — |  | HTTP 404: {"status":404,"title":"Not Found","detail":"Function '20f2537e-8593-4eb9-ad40-60eee3bbaa55': Not found for account 'oYBM |
| `microsoft/phi-3.5-moe-instruct` | ❌ | — |  | HTTP 404: {"status":404,"title":"Not Found","detail":"Function 'e6cab982-62f4-481e-9a7a-3dedb87dbd01': Not found for account 'oYBM |
| `mistralai/codestral-22b-instruct-v0.1` | ❌ | — |  | HTTP 404: {"status":404,"title":"Not Found","detail":"Function '9a10b012-e6df-46fd-83b2-700dcbc75814': Not found for account 'oYBM |
| `mistralai/mistral-7b-instruct-v0.3` | ❌ | — |  | HTTP 404: {"status":404,"title":"Not Found","detail":"Function 'cd89bd68-13e3-47a9-861e-9a62e6e14b05': Not found for account 'oYBM |
| `mistralai/mistral-large` | ❌ | — |  | HTTP 404: {"status":404,"title":"Not Found","detail":"Function '767b5b9a-3f9d-4c1d-86e8-fa861988cee7': Not found for account 'oYBM |
| `mistralai/mistral-large-2-instruct` | ❌ | — |  | HTTP 404: {"status":404,"title":"Not Found","detail":"Function '7fadd4de-e22a-48e4-90e9-f02ef14a74b9': Not found for account 'oYBM |
| `mistralai/mixtral-8x22b-v0.1` | ❌ | — |  | HTTP 404: {"status":404,"title":"Not Found","detail":"Function '39655fc1-9ebc-4b24-963e-6915ea6680de': Not found for account 'oYBM |
| `moonshotai/kimi-k2.6` | ❌ | — |  | HTTP 404: {"status":404,"title":"Not Found","detail":"Function '23d4f03a-b8a6-4adb-a183-7daa083a09cc': Not found for account 'oYBM |
| `nv-mistralai/mistral-nemo-12b-instruct` | ❌ | — |  | HTTP 404: {"status":404,"title":"Not Found","detail":"Function 'f8c05193-d2e2-4f0f-bb4d-7ad70070002b': Not found for account 'oYBM |
| `nvidia/ai-synthetic-video-detector` | ❌ | — |  | HTTP 500: {"type":"urn:nvcf-worker-service:problem-details:internal-server-error", "title":"Internal Server Error", "status":500,  |
| `nvidia/cosmos-reason2-8b` | ❌ | — |  | HTTP 404: {"status":404,"title":"Not Found","detail":"Function 'e199b43b-6c62-4a63-9379-f60e1a953236': Not found for account 'oYBM |
| `nvidia/llama-3.1-nemotron-51b-instruct` | ❌ | — |  | HTTP 404: {"status":404,"title":"Not Found","detail":"Function '5beba52c-65a9-4f46-8cd9-656689a1b205': Not found for account 'oYBM |
| `nvidia/llama-3.1-nemotron-70b-instruct` | ❌ | — |  | HTTP 404: {"status":404,"title":"Not Found","detail":"Function '9b96341b-9791-4db9-a00d-4e43aa192a39': Not found for account 'oYBM |
| `nvidia/llama-3.1-nemotron-ultra-253b-v1` | ❌ | — |  | HTTP 404: {"status":404,"title":"Not Found","detail":"Function '84bf12ff-edbd-4435-baea-0fa6a7453d2e': Not found for account 'oYBM |
| `nvidia/llama3-chatqa-1.5-70b` | ❌ | — |  | HTTP 404: {"status":404,"title":"Not Found","detail":"Function '46594287-38b9-481c-a37f-baa02f2d3ba1': Not found for account 'oYBM |
| `nvidia/mistral-nemo-minitron-8b-8k-instruct` | ❌ | — |  | HTTP 404: {"status":404,"title":"Not Found","detail":"Function '5aa06dd2-0a02-4a5d-be4c-bf88e956965d': Not found for account 'oYBM |
| `nvidia/nemotron-3-super-120b-a12b` | ❌ | — |  | HTTP 404: {"status":404,"title":"Not Found","detail":"Function 'ac74040f-9fc9-4c5e-ac74-279ba5161d69': Not found for account 'oYBM |
| `nvidia/nemotron-4-340b-instruct` | ❌ | — |  | HTTP 404: {"status":404,"title":"Not Found","detail":"Function 'b0fcd392-e905-4ab4-8eb9-aeae95c30b37': Not found for account 'oYBM |
| `nvidia/nemotron-nano-3-30b-a3b` | ❌ | — |  | HTTP 404: {"status":404,"title":"Not Found","detail":"Function '2b2dcd47-c858-425a-9c04-4cacf2eac993': Not found for account 'oYBM |
| `nvidia/riva-translate-4b-instruct` | ❌ | — |  | HTTP 404: {"status":404,"title":"Not Found","detail":"Function 'f35337fa-b4dd-4996-bcba-5476ee01171d': Not found for account 'oYBM |
| `openai/gpt-oss-20b` | ❌ | — |  | HTTP 0: TimeoutError: The read operation timed out |
| `writer/palmyra-creative-122b` | ❌ | — |  | HTTP 404: {"status":404,"title":"Not Found","detail":"Function '00bdd0a7-e38f-4423-9007-c4d8730a3f78': Not found for account 'oYBM |
| `writer/palmyra-fin-70b-32k` | ❌ | — |  | HTTP 404: {"status":404,"title":"Not Found","detail":"Function '316490c6-f1ed-41f9-9da8-3fa9e885653b': Not found for account 'oYBM |
| `writer/palmyra-med-70b` | ❌ | — |  | HTTP 404: {"status":404,"title":"Not Found","detail":"Function 'aab71274-5281-4941-b0b8-20f339d1fc7e': Not found for account 'oYBM |
| `writer/palmyra-med-70b-32k` | ❌ | — |  | HTTP 404: {"status":404,"title":"Not Found","detail":"Function 'd6faa974-3591-49a4-963d-97221d074b2e': Not found for account 'oYBM |
| `zyphra/zamba2-7b-instruct` | ❌ | — |  | HTTP 404: {"status":404,"title":"Not Found","detail":"Function '8378ffb2-51b0-4140-9684-dda1889373e6': Not found for account 'oYBM |
