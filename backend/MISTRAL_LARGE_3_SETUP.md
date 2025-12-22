# Mistral Large 3 Setup Guide

This guide explains how to configure and test **Mistral Large 3** with the Nate API Substrate via OpenRouter.

## 🤖 About Mistral Large 3

**Mistral Large 3 (2512)** is Mistral AI's latest frontier model released December 2025:

- **Architecture**: Granular Mixture of Experts (MoE)
  - 41 billion active parameters
  - 675 billion total parameters
- **Context Window**: 256,000 tokens
- **Capabilities**:
  - ✅ Native function calling (OpenAI-compatible format)
  - ✅ Multimodal (vision support)
  - ✅ Multilingual
  - ✅ Structured output generation
- **NOT a Reasoning Model**: Optimized for "System 1" fast pattern matching
  - Can chain reasoning steps
  - NOT designed for hundreds of tool calls or extended deliberative chains
  - A reasoning version is coming soon from Mistral AI

## 📋 Prerequisites

1. **OpenRouter API Key**: Get one at https://openrouter.ai/keys
2. **Backend running**: Python 3.11+ with dependencies installed
3. **Agent configured**: Run `setup_nate.py` or equivalent to create an agent

## 🚀 Quick Setup

### Step 1: Configure Environment

Copy the Mistral Large 3 configuration example:

```bash
cd backend
cp .env.mistral_large_3 .env
```

Or add these lines to your existing `.env`:

```bash
OPENROUTER_API_KEY=your_openrouter_api_key_here
DEFAULT_LLM_MODEL=mistralai/mistral-large
```

### Step 2: Configure Agent for Mistral Large 3

Run the configuration script:

```bash
cd backend
python configure_mistral_large_3.py
```

This will:
- Set model to `mistralai/mistral-large`
- Configure 256K context window
- Set `reasoning_enabled: False` (correct for this model)
- Configure optimal parameters for function calling

### Step 3: Verify Configuration

Check that the model is correctly identified as non-reasoning:

```bash
python -c "from core.native_reasoning_models import has_native_reasoning; print('Mistral Large 3 is REASONING model:', has_native_reasoning('mistralai/mistral-large'))"
```

Expected output: `Mistral Large 3 is REASONING model: False` ✅

### Step 4: Start the Backend

```bash
cd backend
source venv/bin/activate  # On Windows: venv\Scripts\activate
python api/server.py
```

### Step 5: Start the Frontend

```bash
cd frontend
npm run dev
```

Open http://localhost:5173 and start chatting!

## 🧪 Testing Function Calling

Mistral Large 3 supports native function calling. Test with these prompts:

### Memory Operations
```
Remember that I prefer morning strategy sessions
```
→ Should call `core_memory_append`

```
Search your archival memory for information about quantum computing
```
→ Should call `archival_memory_search`

### Web Tools
```
Search the web for the latest news on AI models
```
→ Should call `web_search`

```
Fetch the content from https://example.com
```
→ Should call `fetch_webpage`

### Multi-Step Tool Chains
```
Search for information about Mistral AI, then save the most interesting fact to your memory
```
→ Should chain `web_search` → `core_memory_append`

## 📊 Model Configuration Details

The configuration script sets these parameters:

```json
{
  "model": "mistralai/mistral-large",
  "temperature": 0.7,
  "max_tokens": 8192,
  "context_window": 256000,
  "reasoning_enabled": false,
  "max_reasoning_tokens": null
}
```

### Why `reasoning_enabled: false`?

Mistral Large 3 is **NOT a reasoning model** like o1 or DeepSeek R1. It's optimized for:
- Fast pattern matching (System 1 thinking)
- Efficient tool calling
- Agentic workflows

It does NOT output extended deliberative reasoning chains like native reasoning models.

## 🔧 Troubleshooting

### Function Calls Not Working

If Mistral Large 3 isn't calling functions:

1. **Check OpenRouter API key**: Make sure `OPENROUTER_API_KEY` is valid
2. **Verify model ID**: Should be `mistralai/mistral-large` (not `mistral-large-3-25-12`)
3. **Check tool definitions**: The substrate automatically provides tools in OpenAI format
4. **Review logs**: Backend logs show tool calls and function execution

### Model Returns Empty Responses

If you get empty responses:

1. **Check context length**: Mistral Large 3 supports 256K tokens
2. **Verify API credits**: Check balance at https://openrouter.ai/credits
3. **Review temperature**: Lower temperature (0.3-0.5) for more deterministic outputs

### Reasoning Fields Appearing

If you see `reasoning` or `reasoning_content` fields (you shouldn't):

1. **Verify detection**: Run the verification command in Step 3
2. **Check model ID**: Make sure it's exactly `mistralai/mistral-large`
3. **Review logs**: Backend should show "STANDARD" mode, not "REASONING"

## 📈 Performance Expectations

### Strengths
- ✅ Fast response times (System 1 optimized)
- ✅ Excellent function calling accuracy
- ✅ Long context handling (256K tokens)
- ✅ Good at tool chaining (3-5 tool calls)

### Limitations
- ❌ NOT designed for extended reasoning chains (hundreds of tokens of thinking)
- ❌ NOT a deliberative reasoning model (no CoT reasoning output)
- ❌ Best for <10 tool calls per turn (not unlimited agentic loops)

### Comparison to Reasoning Models

| Feature | Mistral Large 3 | o1/R1 (Reasoning) |
|---------|----------------|-------------------|
| Function Calling | ✅ Excellent | ✅ Excellent |
| Speed | ⚡ Very Fast | 🐌 Slower |
| Tool Chaining | ✅ Good (3-5 steps) | ✅ Excellent (10+ steps) |
| Extended Reasoning | ❌ No | ✅ Yes |
| Context Window | 256K | 128K-200K |
| Cost | 💰 Lower | 💰💰 Higher |

## 🔗 Resources

- **Mistral AI Docs**: https://docs.mistral.ai/models/mistral-large-3-25-12
- **Function Calling Guide**: https://docs.mistral.ai/capabilities/function_calling
- **OpenRouter Mistral Large 3**: https://openrouter.ai/models/mistralai/mistral-large
- **OpenRouter Docs**: https://openrouter.ai/docs

## 🎯 Best Use Cases

Mistral Large 3 excels at:

1. **Fast agentic workflows** - Quick tool calling for information gathering
2. **Multi-step tasks** - Chaining 3-5 tools efficiently
3. **Long context understanding** - 256K context for extensive conversations
4. **Cost-effective deployment** - Lower cost than reasoning models
5. **Production systems** - Fast, reliable, predictable performance

**NOT recommended for:**
- Extended deliberative reasoning (use o1/R1 instead)
- Complex multi-step planning requiring 10+ tool calls
- Tasks requiring "show your work" style reasoning output

## 📝 Notes

- The substrate automatically detects Mistral Large 3 as a **standard model**
- Function calling uses OpenAI-compatible format (Mistral native format)
- No special prompting needed for tool calling
- The model will NOT output reasoning tokens (by design)

---

**Built for developers testing frontier models on production AI infrastructure.**

*Last Updated: December 2025*
