@echo off
echo ========================================
echo Running Mock API Tests
echo ========================================
echo.

echo [1/9] Basic Chat Completion
curl -X POST http://localhost:8090/v1/chat/completions -H "Content-Type: application/json" -H "Authorization: Bearer sk-test-12345" -d @test_chat.json
echo.
echo.

echo [2/9] GPT-4 Stream
curl -X POST http://localhost:8090/v1/chat/completions -H "Content-Type: application/json" -H "Authorization: Bearer sk-test-12345" -d @test_chat_stream.json
echo.
echo.

echo [3/9] Claude Model
curl -X POST http://localhost:8090/v1/chat/completions -H "Content-Type: application/json" -H "Authorization: Bearer sk-test-12345" -d @test_chat_claude.json
echo.
echo.

echo [4/9] Text Completion
curl -X POST http://localhost:8090/v1/completions -H "Content-Type: application/json" -d @test_completion.json
echo.
echo.

echo [5/9] Embeddings
curl -X POST http://localhost:8090/v1/embeddings -H "Content-Type: application/json" -H "Authorization: Bearer sk-test-12345" -d @test_embeddings.json
echo.
echo.

echo [6/9] Audio Speech (saving to output.mp3)
curl -X POST http://localhost:8090/v1/audio/speech -H "Content-Type: application/json" -d @test_audio_speech.json --output output.mp3
echo.
echo.

echo [7/9] Audio Transcription (requires test_audio.mp3)
echo Skipping - requires actual audio file
echo.

echo [8/9] Gemini Model
curl -X POST http://localhost:8090/v1beta/models/gemini-1.5-flash:generateContent -H "Content-Type: application/json" -H "x-goog-api-key: test-api-key" -d @test_gemini.json
echo.
echo.

echo [9/9] Error 429 Test
curl -X POST http://localhost:8090/v1/chat/completions -H "Content-Type: application/json" -H "Authorization: Bearer sk-test" -d @test_error_429.json
echo.
echo.

echo [10/10] Random Sleep Test
curl -X POST http://localhost:8090/v1/chat/completions -H "Content-Type: application/json" -H "Authorization: Bearer sk-test" -d @test_random_sleep.json
echo.
echo.

echo ========================================
echo All tests completed!
echo ========================================