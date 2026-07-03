import { useState, useEffect, useRef, useCallback } from 'react';
import { uploadDocument, ingestUrl, listDocuments, getOrgId } from '../services/api';
import './AdminPortal.css';

export default function AdminPortal() {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const [urlInput, setUrlInput] = useState('');
  const [uploadStatus, setUploadStatus] = useState(null); // { type: 'loading'|'success'|'error', message }
  const [urlStatus, setUrlStatus] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef(null);
  const orgId = getOrgId();

  // Fetch documents on mount and after successful ingestion
  const fetchDocuments = useCallback(async () => {
    if (!orgId) return;
    try {
      setLoading(true);
      const data = await listDocuments(orgId);
      setDocuments(data.documents || []);
    } catch (err) {
      console.error('Failed to fetch documents:', err);
    } finally {
      setLoading(false);
    }
  }, [orgId]);

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  // ---- File Upload ----
  const handleFileSelect = (e) => {
    const file = e.target.files?.[0];
    if (file) setSelectedFile(file);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file && file.type === 'application/pdf') {
      setSelectedFile(file);
    }
  };

  const handleUpload = async () => {
    if (!selectedFile || !orgId) return;
    setUploadStatus({ type: 'loading', message: 'Uploading and indexing...' });
    try {
      const result = await uploadDocument(selectedFile, orgId);
      setUploadStatus({
        type: 'success',
        message: `${result.name} indexed (${result.chunk_count} chunks)`,
      });
      setSelectedFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
      fetchDocuments();
      setTimeout(() => setUploadStatus(null), 5000);
    } catch (err) {
      setUploadStatus({ type: 'error', message: err.message });
      setTimeout(() => setUploadStatus(null), 5000);
    }
  };

  // ---- URL Ingestion ----
  const handleUrlIngest = async () => {
    if (!urlInput.trim() || !orgId) return;
    setUrlStatus({ type: 'loading', message: 'Scraping and indexing...' });
    try {
      const result = await ingestUrl(urlInput.trim(), orgId);
      setUrlStatus({
        type: 'success',
        message: `${result.name} indexed (${result.chunk_count} chunks)`,
      });
      setUrlInput('');
      fetchDocuments();
      setTimeout(() => setUrlStatus(null), 5000);
    } catch (err) {
      setUrlStatus({ type: 'error', message: err.message });
      setTimeout(() => setUrlStatus(null), 5000);
    }
  };

  const formatFileSize = (bytes) => {
    if (!bytes) return '';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const getStatusBadge = (status) => {
    const map = {
      indexed: 'badge badge-success',
      processing: 'badge badge-warning',
      error: 'badge badge-error',
    };
    return map[status] || 'badge';
  };

  return (
    <div className="admin-portal">
      {/* Header */}
      <div className="admin-header">
        <h2>Knowledge Base Manager</h2>
        <div className="org-badge">{orgId}</div>
      </div>

      {/* Ingestion Cards */}
      <div className="ingestion-section">
        {/* PDF Upload Card */}
        <div className="glass-panel upload-card">
          <div className="card-title">
            <span className="icon">📄</span>
            Upload PDF Document
          </div>

          <div
            className={`drop-zone ${dragOver ? 'drag-over' : ''}`}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            <span className="drop-zone-icon">⬆️</span>
            <div className="drop-zone-text">
              <strong>Click to browse</strong> or drag & drop
              <br />
              <span className="text-xs text-muted">PDF files up to 50MB</span>
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf"
              onChange={handleFileSelect}
            />
          </div>

          {selectedFile && (
            <div className="selected-file animate-fade-in">
              <span className="file-icon">📎</span>
              <span className="file-name">{selectedFile.name}</span>
              <span className="file-size">{formatFileSize(selectedFile.size)}</span>
              <button
                className="remove-btn"
                onClick={() => { setSelectedFile(null); if (fileInputRef.current) fileInputRef.current.value = ''; }}
              >
                ✕
              </button>
            </div>
          )}

          <button
            className="btn btn-primary"
            onClick={handleUpload}
            disabled={!selectedFile || uploadStatus?.type === 'loading'}
          >
            {uploadStatus?.type === 'loading' ? (
              <><span className="spinner" /> Indexing...</>
            ) : (
              '⬆ Upload & Index'
            )}
          </button>

          {uploadStatus && (
            <div className={`upload-progress ${uploadStatus.type === 'success' ? 'upload-success' : ''} ${uploadStatus.type === 'error' ? 'upload-error' : ''}`}>
              {uploadStatus.type === 'loading' && <span className="spinner" />}
              {uploadStatus.type === 'success' && '✓'}
              {uploadStatus.type === 'error' && '✗'}
              {uploadStatus.message}
            </div>
          )}
        </div>

        {/* URL Ingestion Card */}
        <div className="glass-panel url-card">
          <div className="card-title">
            <span className="icon">🌐</span>
            Ingest Web Page
          </div>

          <p className="text-sm text-muted">
            Enter a public URL to scrape, chunk, and index its content.
          </p>

          <div className="url-input-group">
            <input
              type="url"
              className="input"
              placeholder="https://example.com/faq"
              value={urlInput}
              onChange={(e) => setUrlInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleUrlIngest()}
            />
            <button
              className="btn btn-primary"
              onClick={handleUrlIngest}
              disabled={!urlInput.trim() || urlStatus?.type === 'loading'}
            >
              {urlStatus?.type === 'loading' ? (
                <span className="spinner" />
              ) : (
                '🔗 Ingest'
              )}
            </button>
          </div>

          {urlStatus && (
            <div className={`upload-progress ${urlStatus.type === 'success' ? 'upload-success' : ''} ${urlStatus.type === 'error' ? 'upload-error' : ''}`}>
              {urlStatus.type === 'loading' && <span className="spinner" />}
              {urlStatus.type === 'success' && '✓'}
              {urlStatus.type === 'error' && '✗'}
              {urlStatus.message}
            </div>
          )}
        </div>
      </div>

      {/* Documents Table */}
      <div className="glass-panel documents-section">
        <div className="section-header">
          <h3>📋 Indexed Documents</h3>
          <div className="doc-count">{documents.length} document{documents.length !== 1 ? 's' : ''}</div>
        </div>

        {loading ? (
          <div style={{ display: 'flex', justifyContent: 'center', padding: '40px' }}>
            <div className="spinner spinner-lg" />
          </div>
        ) : documents.length === 0 ? (
          <div className="empty-state">
            <span className="empty-state-icon">📂</span>
            <div className="empty-state-text">No documents yet</div>
            <div className="empty-state-subtext">Upload a PDF or ingest a URL to get started</div>
          </div>
        ) : (
          <table className="documents-table">
            <thead>
              <tr>
                <th>Document</th>
                <th>Type</th>
                <th>Status</th>
                <th>Chunks</th>
                <th>Added</th>
              </tr>
            </thead>
            <tbody>
              {documents.map((doc, i) => (
                <tr key={doc.document_id || i} className="animate-fade-in" style={{ animationDelay: `${i * 0.05}s` }}>
                  <td>
                    <div className="doc-name">
                      {doc.type === 'pdf' ? '📄' : '🌐'}
                      {doc.name}
                    </div>
                  </td>
                  <td>
                    <span className="doc-type">{doc.type}</span>
                  </td>
                  <td>
                    <span className={getStatusBadge(doc.status)}>{doc.status}</span>
                  </td>
                  <td className="text-muted">{doc.chunk_count || '—'}</td>
                  <td className="text-muted text-sm">
                    {doc.created_at ? new Date(doc.created_at).toLocaleDateString() : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
