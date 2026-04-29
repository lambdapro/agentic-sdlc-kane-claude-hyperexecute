#!/bin/bash
set -e

# Start Ollama server in background
ollama serve &
OLLAMA_PID=$!
sleep 3
echo "Ollama running (pid $OLLAMA_PID)"
ollama list

# Start LiteLLM proxy (Anthropic format → Ollama)
litellm --config /etc/litellm/config.yaml --port 4000 &
LITELLM_PID=$!
echo "LiteLLM running (pid $LITELLM_PID) on port 4000"

# Wait for LiteLLM to be ready
until curl -sf http://localhost:4000/health > /dev/null 2>&1; do
  sleep 1
done
echo "LiteLLM proxy ready"

# Keep container alive — trap signals for clean shutdown
wait $OLLAMA_PID $LITELLM_PID
