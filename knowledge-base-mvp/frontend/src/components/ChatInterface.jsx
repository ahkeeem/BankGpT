import { useState, useRef, useEffect } from 'react';
import { streamChat, getOrgId } from '../services/api';
import './ChatInterface.css';

const SUGGESTED_QUESTIONS = [
  'What services do you offer?',
  'How do I open an account?',
  'What are the fees and charges?',
  'How can I contact support?',
];

export default function ChatInterface() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [hoveredSource, setHoveredSource] = useState(null);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const abortControllerRef = useRef(null);
  const orgId = getOrgId();

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Focus input on mount
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const handleSend = (questionOverride) => {
    const question = (questionOverride || input).trim();
    if (!question || isStreaming) return;

    // Add user message
    const userMessage = { role: 'user', content: question };
    const assistantMessage = { role: 'assistant', content: '', sources: [], isStreaming: true };

    setMessages((prev) => [...prev, userMessage, assistantMessage]);
    setInput('');
    setIsStreaming(true);

    const controller = streamChat(orgId, question, {
      onToken: (token) => {
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last.role === 'assistant') {
            last.content += token;
          }
          return [...updated];
        });
      },
      onSources: (sources) => {
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last.role === 'assistant') {
            last.sources = sources;
          }
          return [...updated];
        });
      },
      onDone: () => {
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last.role === 'assistant') {
            last.isStreaming = false;
          }
          return [...updated];
        });
        setIsStreaming(false);
      },
      onError: (errorMsg) => {
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last.role === 'assistant') {
            last.content = `⚠ Error: ${errorMsg}`;
            last.isStreaming = false;
          }
          return [...updated];
        });
        setIsStreaming(false);
      },
    });

    abortControllerRef.current = controller;
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const renderMessage = (msg, index) => {
    if (msg.role === 'user') {
      return (
        <div key={index} className="message message-user">
          <div className="message-avatar">👤</div>
          <div className="message-bubble">
            <div className="message-content">{msg.content}</div>
          </div>
        </div>
      );
    }

    return (
      <div key={index} className="message message-assistant">
        <div className="message-avatar">🤖</div>
        <div className="message-bubble">
          {!msg.content && msg.isStreaming ? (
            <div className="thinking-indicator">
              <div className="thinking-dot" />
              <div className="thinking-dot" />
              <div className="thinking-dot" />
            </div>
          ) : (
            <>
              <div className="message-content">
                {msg.content}
                {msg.isStreaming && <span className="typing-cursor" />}
              </div>

              {/* Source Citations */}
              {msg.sources && msg.sources.length > 0 && !msg.isStreaming && (
                <div className="sources-container animate-fade-in">
                  <div className="sources-label">📚 Sources</div>
                  <div className="source-badges">
                    {msg.sources.map((source, si) => (
                      <div
                        key={si}
                        className="source-badge"
                        onMouseEnter={() => setHoveredSource(`${index}-${si}`)}
                        onMouseLeave={() => setHoveredSource(null)}
                      >
                        <span className="source-icon">{source.source_url ? '🌐' : '📄'}</span>
                        {source.name}

                        {hoveredSource === `${index}-${si}` && (
                          <div className="source-tooltip">
                            <div className="source-tooltip-title">{source.name}</div>
                            <div className="source-tooltip-snippet">{source.text_snippet}</div>
                            {source.relevance_score > 0 && (
                              <div className="source-tooltip-score">
                                Relevance: {(source.relevance_score * 100).toFixed(1)}%
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Suggestion chips after first non-streaming assistant message */}
              {!msg.isStreaming && index === messages.length - 1 && messages.length <= 3 && (
                <div className="suggestions animate-fade-in" style={{ animationDelay: '0.3s' }}>
                  {SUGGESTED_QUESTIONS.slice(0, 3).map((q, qi) => (
                    <button
                      key={qi}
                      className="suggestion-chip"
                      onClick={() => handleSend(q)}
                    >
                      {q}
                    </button>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="chat-interface">
      {/* Header */}
      <div className="chat-header">
        <h2>AI Knowledge Assistant</h2>
        <p>Ask questions about your organization's knowledge base</p>
      </div>

      {/* Messages or Welcome */}
      {messages.length === 0 ? (
        <div className="chat-welcome">
          <div className="welcome-icon">💬</div>
          <div className="welcome-title">Start a Conversation</div>
          <div className="welcome-subtitle">
            Ask anything about your indexed documents. I'll find the most relevant information and cite my sources.
          </div>
          <div className="suggestions" style={{ marginTop: '8px' }}>
            {SUGGESTED_QUESTIONS.map((q, i) => (
              <button
                key={i}
                className="suggestion-chip"
                onClick={() => handleSend(q)}
                style={{ animationDelay: `${i * 0.1}s` }}
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="messages-container">
          {messages.map(renderMessage)}
          <div ref={messagesEndRef} />
        </div>
      )}

      {/* Input */}
      <div className="chat-input-area">
        <div className="chat-input-container">
          <input
            ref={inputRef}
            type="text"
            className="chat-input"
            placeholder="Ask a question about your knowledge base..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isStreaming}
          />
          <button
            className="send-button"
            onClick={() => handleSend()}
            disabled={!input.trim() || isStreaming}
            aria-label="Send message"
          >
            {isStreaming ? '⏸' : '➤'}
          </button>
        </div>
      </div>
    </div>
  );
}
