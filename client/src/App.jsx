import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { io } from 'socket.io-client';
import './styles.css';

const backendUrl = import.meta.env.MODE === 'development'
    ? 'http://localhost:5001'
    : import.meta.env.VITE_BACKEND_URL;;


function App() {
    const [url, setUrl] = useState('');
    const [days, setDays] = useState('7');
    const [customDate, setCustomDate] = useState('');
    const [email, setEmail] = useState('');
    const [loading, setLoading] = useState(false);
    const [message, setMessage] = useState('');
    const [progress, setProgress] = useState(0);
    const [reviews, setReviews] = useState([]);
    const [sentiment, setSentiment] = useState('');
    const [swot, setSwot] = useState({ strengths: [], weaknesses: [], opportunities: [], threats: [] });
    const [sessionId, setSessionId] = useState('');
    const [error, setError] = useState('');
    const socketRef = useRef(null);
    const [connectionStatus, setConnectionStatus] = useState('connecting');

    useEffect(() => {
        const id = Math.random().toString(36).substr(2, 9);
        setSessionId(id);
        console.log('Generated session ID:', id);

        // Initialize socket connection with better config
        socketRef.current = io(backendUrl, {
            transports: ['websocket', 'polling'],
            timeout: 20000,
            reconnection: true,
            reconnectionAttempts: 5,
            reconnectionDelay: 1000
        });

        socketRef.current.on('connect', () => {
            console.log('✅ Socket connected with ID:', socketRef.current.id);
            setConnectionStatus('connected');
            setError('');

            // Join session immediately after connection
            if (id) {
                console.log('🏠 Joining session:', id);
                socketRef.current.emit('join_session', { sessionId: id });
            }
        });

        // Add session joined confirmation
        socketRef.current.on('session_joined', (data) => {
            console.log('✅ Session joined confirmed:', data.sessionId);
        });

        socketRef.current.on('connect_error', (error) => {
            console.error('❌ Socket connection error:', error);
            setError('Unable to connect to server. Please check if the backend is running.');
        });

        socketRef.current.on('disconnect', (reason) => {
            console.log('🔌 Socket disconnected:', reason);
            setConnectionStatus('disconnected');
        });

        socketRef.current.on('status_update', (data) => {
            console.log('📊 Status update:', data);
            setMessage(data.status);
            setProgress(data.progress);

            if (data.error) {
                setLoading(false);
                setError(data.status);
            }

            if (
                data.progress >= 99 ||
                (data.status && data.status.toLowerCase().includes("analysis complete"))
              ) {
                setLoading(false);
              }
              
        });
        // Improved review handling
        socketRef.current.on('review', (newReviews) => {
            console.log('📝 Received reviews:', newReviews);

            if (!Array.isArray(newReviews)) {
                console.warn('⚠️ Received non-array reviews:', newReviews);
                return;
            }

            if (newReviews.length === 0) {
                console.warn('⚠️ Received empty reviews array');
                return;
            }

            setReviews((prevReviews) => {
                const prevCount = prevReviews.length;

                // Create a Set of existing review identifiers to avoid duplicates
                const existingReviewIds = new Set(
                    prevReviews.map(r => `${r.author}_${r.date}_${r.rating}`)
                );

                // Filter out duplicates
                const uniqueNewReviews = newReviews.filter(review => {
                    const reviewId = `${review.author}_${review.date}_${review.rating}`;
                    return !existingReviewIds.has(reviewId);
                });

                const updatedReviews = [...prevReviews, ...uniqueNewReviews];
                console.log(`📈 Reviews updated: ${prevCount} → ${updatedReviews.length} (+${uniqueNewReviews.length} new)`);

                return updatedReviews;
            });
        });

        socketRef.current.on('sentiment_update', (data) => {
            console.log('💭 Sentiment update:', data);
            setSentiment(data.text);
        });

        socketRef.current.on('swot_update', (data) => {
            console.log('📊 SWOT update:', data);
            setSwot((prev) => ({ ...prev, ...data }));
        });

        // Debug: log all socket events
        socketRef.current.onAny((event, ...args) => {
            console.log(`🎧 Socket event: ${event}`, args);
        });

        return () => {
            if (socketRef.current) {
                console.log('🔌 Disconnecting socket');
                socketRef.current.disconnect();
            }
        };
    }, []);

    useEffect(() => {
        if (sessionId && socketRef.current && socketRef.current.connected) {
            console.log('Joining session:', sessionId);
            socketRef.current.emit('join_session', { sessionId });
        }
    }, [sessionId, socketRef.current?.connected]);

    const handleSubmit = async () => {
        // Validation
        if (!url.trim()) {
            setError('Please enter a Google Maps URL');
            return;
        }
        if (!email.trim()) {
            setError('Please enter your email address');
            return;
        }
        if (days === 'custom' && !customDate) {
            setError('Please select a custom date');
            return;
        }

        // Validate email format
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(email)) {
            setError('Please enter a valid email address');
            return;
        }

        // Validate URL format
        if (!url.includes('google.com/maps') && !url.includes('goo.gl')) {
            setError('Please enter a valid Google Maps URL');
            return;
        }

        setLoading(true);
        setError('');
        setMessage('Starting analysis...');
        setProgress(0);
        setReviews([]);
        setSentiment('');
        setSwot({ strengths: [], weaknesses: [], opportunities: [], threats: [] });

        console.log('Starting new analysis, reviews reset');

        try {
            await axios.post('${backendUrl}/api/scrape', {
                url: url.trim(),
                days,
                customDate,
                email: email.trim(),
                sessionId
            });
        } catch (err) {
            console.error(err);
            setError('Error connecting to server. Please check if the backend is running.');
            setLoading(false);
        }
    };

    const handleCancel = () => {
        if (socketRef.current) {
            socketRef.current.emit('cancel_scraping', { sessionId });
        }
        setLoading(false);
        setMessage('Scraping cancelled by user.');
        setProgress(0);
    };

    const handleReset = () => {
        setUrl('');
        setDays('7');
        setCustomDate('');
        setEmail('');
        setLoading(false);
        setMessage('');
        setProgress(0);
        setReviews([]);
        setSentiment('');
        setSwot({ strengths: [], weaknesses: [], opportunities: [], threats: [] });
        setError('');
    };

    const downloadCSV = async () => {
        if (!reviews.length) {
            setError('No reviews available to download');
            return;
        }

        try {
            const res = await axios.get(`${backendUrl}/api/download-csv/${sessionId}`, {
                responseType: 'blob'
            });

            const url = window.URL.createObjectURL(new Blob([res.data]));
            const link = document.createElement('a');
            link.href = url;
            link.setAttribute('download', `reviews_${sessionId}.csv`);
            document.body.appendChild(link);
            link.click();
            link.remove();
            window.URL.revokeObjectURL(url);
        } catch (err) {
            console.error(err);
            setError('Failed to download CSV file');
        }
    };

    const getRatingClass = (rating) => {
        if (rating >= 4) return 'high';
        if (rating >= 3) return 'medium';
        return 'low';
    };

    const getStats = () => {
        if (!reviews.length) return null;

        const totalReviews = reviews.length;
        const averageRating = (reviews.reduce((sum, r) => sum + r.rating, 0) / totalReviews).toFixed(1);
        const highRatings = reviews.filter(r => r.rating >= 4).length;
        const lowRatings = reviews.filter(r => r.rating <= 2).length;

        return { totalReviews, averageRating, highRatings, lowRatings };
    };

    const stats = getStats();

    return (
        <div className="container">
            <h1>🔍 DoWell Google Reviews Analyzer</h1>

            <div className="form-section">
                <div className="form-group">
                    <input
                        placeholder="Enter Google Maps URL (e.g., https://maps.google.com/...)"
                        value={url}
                        onChange={(e) => setUrl(e.target.value)}
                        className={error && !url.trim() ? 'error' : ''}
                    />
                </div>

                <div className="form-group">
                    <select value={days} onChange={(e) => setDays(e.target.value)}>
                        <option value="7">Last 7 days</option>
                        <option value="15">Last 15 days</option>
                        <option value="30">Last 30 days</option>
                        <option value="90">Last 90 days</option>
                        <option value="custom">Custom date range</option>
                    </select>
                </div>

                {days === 'custom' && (
                    <div className="form-group">
                        <input
                            type="date"
                            value={customDate}
                            onChange={(e) => setCustomDate(e.target.value)}
                            max={new Date().toISOString().split('T')[0]}
                            className="fade-in"
                        />
                    </div>
                )}

                <div className="form-group">
                    <input
                        type="email"
                        placeholder="Your email address"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        className={error && !email.trim() ? 'error' : ''}
                    />
                </div>

                {error && (
                    <div className="alert error">
                        {error}
                    </div>
                )}

                <div className="button-group">
                    <button
                        className="btn primary"
                        onClick={handleSubmit}
                        disabled={loading}
                    >
                        {loading && <span className="loading-spinner"></span>}
                        {loading ? 'Analyzing...' : '🚀 Start Analysis'}
                    </button>

                    {loading && (
                        <button className="btn secondary" onClick={handleCancel}>
                            ❌ Cancel
                        </button>
                    )}

                    <button className="btn secondary" onClick={handleReset}>
                        🔄 Reset
                    </button>
                </div>
            </div>

            {(loading || progress > 0) && (
                <div className="progress-container">
                    <div className="progress">
                        <div className="progress-bar" style={{ width: `${progress}%` }}></div>
                    </div>
                    {message && (
                        <div className="status-message">
                            {message}
                        </div>
                    )}
                </div>
            )}

            {stats && (
                <div className="stats-grid fade-in">
                    <div className="stat-card">
                        <span className="stat-number">{stats.totalReviews}</span>
                        <span className="stat-label">Total Reviews</span>
                    </div>
                    <div className="stat-card">
                        <span className="stat-number">{stats.averageRating}⭐</span>
                        <span className="stat-label">Average Rating</span>
                    </div>
                    <div className="stat-card">
                        <span className="stat-number">{stats.highRatings}</span>
                        <span className="stat-label">High Ratings (4-5★)</span>
                    </div>
                    <div className="stat-card">
                        <span className="stat-number">{stats.lowRatings}</span>
                        <span className="stat-label">Low Ratings (1-2★)</span>
                    </div>
                </div>
            )}

            {reviews.length > 0 && (
                <div className="card">
                    <div className="card-header">
                        <h2 className="card-title">
                            📝 Reviews ({reviews.length})
                        </h2>
                        <button className="download-btn" onClick={downloadCSV}>
                            📥 Download CSV
                        </button>
                    </div>
                    <div className="card-content">
                        <div className="table-container">
                            <table className="reviews-table">
                                <thead>
                                    <tr>
                                        <th>Date</th>
                                        <th>Author</th>
                                        <th>Rating</th>
                                        <th>Review</th>
                                        <th>Photo</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {reviews.map((review, index) => (
                                        <tr key={index} className="slide-in">
                                            <td>{review.date}</td>
                                            <td>
                                                <strong>{review.author}</strong>
                                            </td>
                                            <td>
                                                <span className={`rating ${getRatingClass(review.rating)}`}>
                                                    {review.rating}⭐
                                                </span>
                                            </td>
                                            <td>
                                                <div style={{ maxWidth: '300px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                                    {review.text || 'No text provided'}
                                                </div>
                                            </td>
                                            <td>
                                            {review.photos && review.photos.length > 0 ? (
                                                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                                                {review.photos.map((url, idx) => (
                                                    <img
                                                    key={idx}
                                                    src={url}
                                                    alt={`Review image ${idx + 1}`}
                                                    style={{ height: '50px', borderRadius: '4px', objectFit: 'cover' }}
                                                    />
                                                ))}
                                                </div>
                                            ) : (
                                                <span style={{ color: 'var(--text-secondary)' }}>—</span>
                                            )}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            )}

            {sentiment && (
                <div className="card">
                    <div className="card-header">
                        <h2 className="card-title">💭 Sentiment Analysis</h2>
                    </div>
                    <div className="card-content">
                        <div className="sentiment-analysis">
                            <h2>Overall Sentiment</h2>
                            <p>{sentiment}</p>
                        </div>
                    </div>
                </div>
            )}

            {Object.values(swot).some(arr => arr.length > 0) && (
                <div className="card">
                    <div className="card-header">
                        <h2 className="card-title">📊 SWOT Analysis</h2>
                    </div>
                    <div className="card-content">
                        <div className="swot-grid">
                            {Object.entries(swot).map(([key, items]) => (
                                items.length > 0 && (
                                    <div key={key} className={`swot-box ${key} fade-in`}>
                                        <h3>
                                            {key === 'strengths' && '💪'}
                                            {key === 'weaknesses' && '⚠️'}
                                            {key === 'opportunities' && '🚀'}
                                            {key === 'threats' && '⚡'}
                                            {key.charAt(0).toUpperCase() + key.slice(1)}
                                        </h3>
                                        <ul>
                                            {items.map((item, index) => (
                                                <li key={index}>{item}</li>
                                            ))}
                                        </ul>
                                    </div>
                                )
                            ))}
                        </div>
                    </div>
                </div>
            )}

            {!loading && !reviews.length && !error && (
                <div className="empty-state">
                    <h3>Ready to analyze reviews! 🎯</h3>
                    <p>Enter a Google Maps URL above to get started with your review analysis.</p>
                </div>
            )}
        </div>
    );
}

export default App;