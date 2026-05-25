# Vercel AI SDK — Providers (Full Documentation)

**Source:** https://ai-sdk.dev/providers/ai-sdk-providers  
**Fetched:** 2026-05-24

---

## Official Providers (v6, Latest)

### Primary Providers

| Provider | Package |
|----------|---------|
| Vercel AI Gateway | `ai` (built-in `gateway`) |
| OpenAI | `@ai-sdk/openai` |
| Anthropic | `@ai-sdk/anthropic` |
| Azure OpenAI | `@ai-sdk/azure` |
| Google Generative AI | `@ai-sdk/google` |
| Google Vertex AI | `@ai-sdk/google-vertex` |
| xAI Grok | `@ai-sdk/xai` |
| Amazon Bedrock | `@ai-sdk/amazon-bedrock` |
| Groq | `@ai-sdk/groq` |
| Mistral AI | `@ai-sdk/mistral` |
| Cohere | `@ai-sdk/cohere` |
| DeepSeek | `@ai-sdk/deepseek` |
| Together.ai | `@ai-sdk/togetherai` |
| Fireworks | `@ai-sdk/fireworks` |
| DeepInfra | `@ai-sdk/deepinfra` |
| Fal AI | `@ai-sdk/fal` |
| Luma AI | `@ai-sdk/luma` |
| Baseten | `@ai-sdk/baseten` |
| Hugging Face | `@ai-sdk/huggingface` |

### Specialized Media Providers

| Provider | Capability |
|----------|-----------|
| Black Forest Labs | Image generation |
| ElevenLabs | Text-to-speech |
| AssemblyAI | Speech-to-text |
| Deepgram | Audio processing |
| LMNT | Voice synthesis |
| Rev.ai | Transcription |
| Gladia | Audio transcription |

### Additional Providers

Voyage AI (embeddings), Perplexity (search), Moonshot AI (Kimi), Alibaba (Qwen), Cerebras, Replicate, Prodia, ByteDance, Kling AI, Hume

### OpenAI-Compatible

LM Studio, NVIDIA NIM, Clarifai, Heroku

---

## Notable Models (as of fetch date)

| Provider | Models |
|----------|--------|
| OpenAI | GPT-5.5, GPT-4o, GPT-4o-mini |
| Anthropic | Claude Opus 4.7, Claude Sonnet 4.6, Claude Haiku |
| Google | Gemini 3.1 Pro Preview, Gemini 2.5 Pro/Flash |
| Mistral | Pixtral Large, Magistral |
| Groq | Llama 4 Scout, Llama 3.3-70B, DeepSeek R1 |
| Cohere | Command A (2025), Command R+ |
| DeepSeek | DeepSeek Chat, DeepSeek Reasoner |

---

## Community Providers (50+)

Including:
- Ollama (local models)
- Cloudflare Workers AI
- Portkey (API routing)
- OpenRouter (model aggregator)
- Anthropic Vertex
- Qwen
- llama.cpp
- MCP Sampling AI Provider

---

## Observability Integrations (18+)

Langfuse, LangSmith, Helicone, and others.

---

## Adapter Support

- LangChain
- LlamaIndex

---

## Usage Example (Anthropic Provider)

```typescript
import { anthropic } from '@ai-sdk/anthropic';
import { generateText } from 'ai';

const { text } = await generateText({
  model: anthropic('claude-sonnet-4-6'),
  prompt: 'Write a vegetarian lasagna recipe for 4 people.',
});
```

---

## Key Point for This Project

The Anthropic provider (`@ai-sdk/anthropic`) is a **TypeScript npm package** wrapping the Anthropic API. There is no Python equivalent. The `anthropic==0.96.0` in `pyproject.toml` is the official Python SDK from Anthropic directly — it is not related to the Vercel AI SDK.

The Vercel AI SDK's provider abstraction is a TypeScript-only concern.
