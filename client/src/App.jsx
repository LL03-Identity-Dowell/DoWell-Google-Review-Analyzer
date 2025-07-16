// Enhanced Google Reviews Analyzer with real-time updates
// Note: This component requires socket.io-client to be loaded
// Add this script tag to your HTML: <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.js"></script>

import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
    Search,
    Mail,
    Calendar,
    Globe,
    Download,
    RotateCcw,
    X,
    Play,
    Star,
    TrendingUp,
    TrendingDown,
    BarChart3,
    MessageSquare,
    Users,
    AlertCircle,
    CheckCircle2,
    Loader2,
    Image as ImageIcon,
    Eye,
    Building2,
    MapPin,
    Phone,
    ExternalLink,
    Clock,
    FileText,
    FileDown,
    ChevronDown,
    FileSpreadsheet,
    Send
} from 'lucide-react';



const backendUrl = 'https://googlereviewanalysis.uxlivinglab.org'
// Animation variants
const containerVariants = {
    hidden: { opacity: 0 },
    visible: {
        opacity: 1,
        transition: {
            duration: 0.6,
            staggerChildren: 0.1
        }
    }
};

const itemVariants = {
    hidden: { opacity: 0, y: 20 },
    visible: {
        opacity: 1,
        y: 0,
        transition: { duration: 0.5 }
    }
};

const slideInVariants = {
    hidden: { opacity: 0, x: -20 },
    visible: {
        opacity: 1,
        x: 0,
        transition: { duration: 0.3 }
    }
};

// ErrorBoundary to catch render errors and display a fallback UI
class ErrorBoundary extends React.Component {
    constructor(props) {
        super(props);
        this.state = { hasError: false, error: null, errorInfo: null };
    }
    static getDerivedStateFromError(error) {
        return { hasError: true, error };
    }
    componentDidCatch(error, errorInfo) {
        this.setState({ errorInfo });
        // Optionally log error to an error reporting service
        console.error('ErrorBoundary caught an error:', error, errorInfo);
    }
    render() {
        if (this.state.hasError) {
            return (
                <div style={{ padding: 40, color: 'red', background: '#fff0f0', minHeight: '100vh' }}>
                    <h1>Something went wrong.</h1>
                    <pre style={{ whiteSpace: 'pre-wrap' }}>{this.state.error && this.state.error.toString()}</pre>
                    {this.state.errorInfo && (
                        <details style={{ whiteSpace: 'pre-wrap' }}>
                            {this.state.errorInfo.componentStack}
                        </details>
                    )}
                </div>
            );
        }
        return this.props.children;
    }
}

function App() {
    const [csvFile, setCsvFile] = useState(null);
    const [urls, setUrls] = useState([]);
    const [days, setDays] = useState('7');
    const [customDate, setCustomDate] = useState('');
    const [email, setEmail] = useState('');
    const [loading, setLoading] = useState(false);
    const [message, setMessage] = useState('');
    const [progress, setProgress] = useState(0);
    const [activeTab, setActiveTab] = useState(0);
    const [results, setResults] = useState({}); // Store results for each URL
    const [sentiment, setSentiment] = useState('');
    const [swot, setSwot] = useState({ strengths: [], weaknesses: [], opportunities: [], threats: [] });
    const [sessionId, setSessionId] = useState('');
    const [error, setError] = useState('');
    const [csvError, setCsvError] = useState('');
    const socketRef = useRef(null);
    const [connectionStatus, setConnectionStatus] = useState('connecting');
    const [businessDetails, setBusinessDetails] = useState({});
    const [showDownloadDropdown, setShowDownloadDropdown] = useState(false);
    const [sendingEmail, setSendingEmail] = useState(false);

    useEffect(() => {
        const id = Math.random().toString(36).substr(2, 9);
        setSessionId(id);
        console.log('Generated session ID:', id);

        // Debug: Check if window.io and backendUrl are available
        console.log('About to initialize socket:', typeof window !== 'undefined' ? window.io : null, backendUrl);

        // Close download dropdown when clicking outside
        const handleClickOutside = (event) => {
            if (showDownloadDropdown && !event.target.closest('.download-dropdown')) {
                setShowDownloadDropdown(false);
            }
        };

        document.addEventListener('mousedown', handleClickOutside);

        // Initialize socket connection with proper configuration
        const io = typeof window !== 'undefined' ? window.io : null;
        if (io) {
            try {
                socketRef.current = io(backendUrl, {
                    path: '/socket.io/',
                    transports: ['websocket', 'polling'],
                    timeout: 20000,
                    reconnection: true,
                    reconnectionAttempts: 5,
                    reconnectionDelay: 1000,
                    reconnectionDelayMax: 5000,
                    maxReconnectionAttempts: 5,
                    forceNew: true,
                    secure: window.location.protocol === 'https:',
                    rejectUnauthorized: false
                });
                console.log('Socket initialized:', socketRef.current);
                // Log the socket object after connect
                console.log('Socket object after connect:', socketRef.current);
            } catch (e) {
                console.error('Socket initialization error:', e);
            }

            // Add global error handlers
            window.addEventListener('error', function(e) {
                console.error('Global error:', e);
            });
            window.addEventListener('unhandledrejection', function(e) {
                console.error('Unhandled promise rejection:', e);
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
                setConnectionStatus('error');
                setError('Unable to connect to server. Please check if the backend is running.');
            });

            socketRef.current.on('disconnect', (reason) => {
                console.log('🔌 Socket disconnected:', reason);
                setConnectionStatus('disconnected');
            });

            socketRef.current.on('reconnect', (attemptNumber) => {
                console.log('🔄 Socket reconnected after', attemptNumber, 'attempts');
                setConnectionStatus('connected');
                setError('');

                // Rejoin session after reconnection
                if (id) {
                    socketRef.current.emit('join_session', { sessionId: id });
                }
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

            // Improved review handling for multiple URLs
            socketRef.current.on('review', (data) => {
                console.log('📝 Received reviews:', data);
                const { url, reviews: newReviews } = data;
                // Defensive: ensure newReviews is an array
                if (!Array.isArray(newReviews)) {
                    console.warn('⚠️ Received non-array reviews:', newReviews);
                    return;
                }
                if (newReviews.length === 0) {
                    console.warn('⚠️ Received empty reviews array');
                    return;
                }
                // Defensive: filter out malformed reviews
                const safeReviews = newReviews.filter(r => r && typeof r === 'object' && !Array.isArray(r));
                safeReviews.forEach(review => {
                    if (!Array.isArray(review.photo)) {
                        review.photo = [];
                    }
                });
                setResults(prevResults => {
                    const currentUrlResults = prevResults[url] || { reviews: [], businessDetails: {}, sentiment: '', swot: {} };
                    // Create a Set of existing review identifiers to avoid duplicates
                    const existingReviewIds = new Set(
                        Array.isArray(currentUrlResults.reviews) ? currentUrlResults.reviews.map(r => `${r.author}_${r.date}_${r.rating}`) : []
                    );
                    // Filter out duplicates
                    const uniqueNewReviews = safeReviews.filter(review => {
                        const reviewId = `${review.author}_${review.date}_${review.rating}`;
                        return !existingReviewIds.has(reviewId);
                    });
                    const updatedReviews = [...currentUrlResults.reviews, ...uniqueNewReviews];
                    console.log(`📈 Reviews updated for ${url}: ${currentUrlResults.reviews.length} → ${updatedReviews.length} (+${uniqueNewReviews.length} new)`);
                    return {
                        ...prevResults,
                        [url]: {
                            ...currentUrlResults,
                            reviews: updatedReviews
                        }
                    };
                });
            });

            socketRef.current.on('sentiment_update', (data) => {
                console.log('💭 Sentiment update:', data);
                const { url, sentiment: sentimentText } = data;
                setResults(prevResults => ({
                    ...prevResults,
                    [url]: {
                        ...prevResults[url],
                        sentiment: sentimentText
                    }
                }));
            });

            socketRef.current.on('swot_update', (data) => {
                console.log('📊 SWOT update:', data);
                const { url, swot: swotData } = data;
                setResults(prevResults => ({
                    ...prevResults,
                    [url]: {
                        ...prevResults[url],
                        swot: { ...prevResults[url]?.swot, ...swotData }
                    }
                }));
            });

            socketRef.current.on('business_details', (data) => {
                console.log('🏢 Business details received:', data);
                const { url, businessDetails: details } = data;
                setResults(prevResults => ({
                    ...prevResults,
                    [url]: {
                        ...prevResults[url],
                        businessDetails: details
                    }
                }));
            });

            // Debug: log all socket events
            socketRef.current.onAny((event, ...args) => {
                console.log(`🎧 Socket event: ${event}`, args);
            });
        } else {
            // Fallback if socket.io is not available
            setConnectionStatus('error');
            setError('Socket.io library not found. Please ensure it is loaded.');
        }

        return () => {
            document.removeEventListener('mousedown', handleClickOutside);
            if (socketRef.current) {
                console.log('🔌 Disconnecting socket');
                socketRef.current.disconnect();
            }
        };
    }, []);

    const handleCsvFileChange = (event) => {
        const file = event.target.files[0];
        if (!file) return;

        // Check file type
        if (file.type !== 'text/csv' && !file.name.endsWith('.csv')) {
            setCsvError('Please select a valid CSV file');
            return;
        }

        const reader = new FileReader();
        reader.onload = (e) => {
            try {
                const csvText = e.target.result;
                const lines = csvText.split('\n');
                const urls = [];
                
                // Skip header row and process each line
                for (let i = 1; i < lines.length; i++) {
                    const line = lines[i].trim();
                    if (line) {
                        const columns = line.split(',');
                        const url = columns[0]?.trim();
                        if (url && (url.includes('google.com/maps') || url.includes('goo.gl'))) {
                            urls.push(url);
                        }
                    }
                }

                if (urls.length === 0) {
                    setCsvError('No valid Google Maps URLs found in the CSV file');
                    return;
                }

                if (urls.length > 10000) {
                    setCsvError('CSV file contains more than 10,000 entries. Please use a smaller file.');
                    return;
                }

                setUrls(urls);
                setCsvFile(file);
                setCsvError('');
                console.log(`📄 CSV processed: ${urls.length} URLs found`);
            } catch (error) {
                console.error('Error processing CSV:', error);
                setCsvError('Error processing CSV file. Please check the file format.');
            }
        };
        reader.readAsText(file);
    };

    const handleSubmit = async () => {
        // Validation
        if (!csvFile) {
            setError('Please select a CSV file');
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

        setLoading(true);
        setError('');
        setCsvError('');
        setMessage('Starting analysis...');
        setProgress(0);
        setResults({});
        setActiveTab(0);

        console.log('Starting new analysis for multiple URLs');

        try {
            const response = await fetch(`${backendUrl}/api/scrape-bulk`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    urls: urls,
                    days,
                    customDate,
                    email: email.trim(),
                    sessionId
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            console.log('API response:', data);
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
        setCsvFile(null);
        setUrls([]);
        setDays('7');
        setCustomDate('');
        setEmail('');
        setLoading(false);
        setMessage('');
        setProgress(0);
        setResults({});
        setActiveTab(0);
        setError('');
        setCsvError('');
        setShowDownloadDropdown(false);
        setSendingEmail(false);
    };

    const downloadAllResults = async (format) => {
        if (Object.keys(results).length === 0) {
            setError('No results available to download');
            return;
        }

        try {
            const response = await fetch(`${backendUrl}/api/download-bulk/${sessionId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    results,
                    format,
                    email: email.trim()
                })
            });

            if (!response.ok) {
                throw new Error(`Failed to download ${format.toUpperCase()}`);
            }

            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.setAttribute('download', `google_reviews_analysis_${sessionId}.${format.toLowerCase()}`);
            document.body.appendChild(link);
            link.click();
            link.remove();
            window.URL.revokeObjectURL(url);
            
            setShowDownloadDropdown(false);
        } catch (err) {
            console.error(err);
            setError(`Failed to download ${format.toUpperCase()} file`);
        }
    };

    const sendEmailResults = async () => {
        if (Object.keys(results).length === 0) {
            setError('No results available to send');
            return;
        }

        if (!email.trim()) {
            setError('Please enter your email address');
            return;
        }

        setSendingEmail(true);
        setError('');

        try {
            const response = await fetch(`${backendUrl}/api/send-email`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    results,
                    email: email.trim(),
                    sessionId
                })
            });

            if (!response.ok) {
                throw new Error('Failed to send email');
            }

            const data = await response.json();
            console.log('Email sent successfully:', data);
            setMessage('Results sent to your email successfully!');
        } catch (err) {
            console.error(err);
            setError('Failed to send email. Please try again.');
        } finally {
            setSendingEmail(false);
        }
    };

    const getRatingClass = (rating) => {
        if (rating >= 4) return 'text-green-600 bg-green-50';
        if (rating >= 3) return 'text-yellow-600 bg-yellow-50';
        return 'text-red-600 bg-red-50';
    };

    const getStats = (url) => {
        const urlResults = results[url];
        if (!urlResults || !Array.isArray(urlResults.reviews) || urlResults.reviews.length === 0) return null;
        const reviews = Array.isArray(urlResults.reviews) ? urlResults.reviews : [];
        const totalReviews = reviews.length;
        // const averageRating = (reviews.reduce((sum, r) => sum + r.rating, 0) / totalReviews).toFixed(1);
        const averageRating = totalReviews > 0
            ? (reviews.reduce((sum, r) => sum + r.rating, 0) / totalReviews).toFixed(1)
            : 'N/A';
        const highRatings = reviews.filter(r => r.rating >= 4).length;
        const lowRatings = reviews.filter(r => r.rating <= 2).length;

        return { totalReviews, averageRating, highRatings, lowRatings };
    };

    const stats = getStats();

    const ConnectionIndicator = () => (
        <motion.div
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            className={`flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium ${connectionStatus === 'connected'
                ? 'bg-green-100 text-green-800'
                : connectionStatus === 'connecting'
                    ? 'bg-yellow-100 text-yellow-800'
                    : connectionStatus === 'error'
                        ? 'bg-red-100 text-red-800'
                        : 'bg-gray-100 text-gray-800'
                }`}
        >
            <div className={`w-2 h-2 rounded-full ${connectionStatus === 'connected'
                ? 'bg-green-500'
                : connectionStatus === 'connecting'
                    ? 'bg-yellow-500 animate-pulse'
                    : connectionStatus === 'error'
                        ? 'bg-red-500'
                        : 'bg-gray-500'
                }`} />
            {connectionStatus === 'connected' && 'Connected'}
            {connectionStatus === 'connecting' && 'Connecting...'}
            {connectionStatus === 'disconnected' && 'Disconnected'}
            {connectionStatus === 'error' && 'Connection Error'}
        </motion.div>
    );

    return (
        <div className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-purple-50">
            <motion.div
                className="container mx-auto px-4 py-8 max-w-6xl"
                variants={containerVariants}
                initial="hidden"
                animate="visible"
            >
                {/* Header */}
                <motion.div
                    className="text-center mb-12"
                    variants={itemVariants}
                >
                    <div className="flex items-center justify-center gap-3 mb-4">
                        <div className="p-3 bg-gradient-to-r from-blue-500 to-purple-600 rounded-2xl">
                            <Search className="w-8 h-8 text-white" />
                        </div>
                        <h1 className="text-4xl font-bold bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">
                            DoWell Google Reviews Extractor
                        </h1>
                    </div>
                    <p className="text-gray-600 text-lg">
                        Extract Google Reviews from any business
                    </p>
                    <div className="flex justify-center mt-6">
                        <ConnectionIndicator />
                    </div>
                </motion.div>

                {/* Form Section */}
                <motion.div
                    className="bg-white rounded-3xl shadow-xl p-8 mb-8 border border-gray-100"
                    variants={itemVariants}
                >
                    <div className="grid gap-6">
                        {/* CSV File Input */}
                        <div className="space-y-2">
                            <label className="flex items-center gap-2 text-sm font-medium text-gray-700">
                                <FileSpreadsheet className="w-4 h-4" />
                                CSV File with Google Maps URLs
                            </label>
                            <div className="relative">
                                <input
                                    type="file"
                                    accept=".csv"
                                    onChange={handleCsvFileChange}
                                    className={`w-full px-4 py-3 border rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all ${csvError ? 'border-red-300 bg-red-50' : 'border-gray-300'}`}
                                />
                            </div>
                            {csvFile && (
                                <div className="flex items-center gap-2 p-3 bg-green-50 border border-green-200 rounded-xl text-green-700">
                                    <CheckCircle2 className="w-5 h-5 flex-shrink-0" />
                                    <span className="text-sm">
                                        {csvFile.name} - {urls.length} URLs loaded
                                    </span>
                                </div>
                            )}
                        </div>

                        {/* Date Range and Email Row */}
                        <div className="grid md:grid-cols-2 gap-6">
                            {/* Date Range */}
                            <div className="space-y-2">
                                <label className="flex items-center gap-2 text-sm font-medium text-gray-700">
                                    <Calendar className="w-4 h-4" />
                                    Date Range
                                </label>
                                <select
                                    value={days}
                                    onChange={(e) => setDays(e.target.value)}
                                    className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all"
                                >
                                    <option value="7">Last 7 days</option>
                                    <option value="15">Last 15 days</option>
                                    <option value="30">Last 30 days</option>
                                    <option value="90">Last 90 days</option>
                                    <option value="custom">Custom date range</option>
                                </select>
                            </div>

                            {/* Email */}
                            <div className="space-y-2">
                                <label className="flex items-center gap-2 text-sm font-medium text-gray-700">
                                    <Mail className="w-4 h-4" />
                                    Email Address
                                </label>
                                <div className="relative">
                                    <input
                                        type="email"
                                        placeholder="your@email.com"
                                        value={email}
                                        onChange={(e) => setEmail(e.target.value)}
                                        className={`w-full px-4 py-3 border rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all ${error && !email.trim() ? 'border-red-300 bg-red-50' : 'border-gray-300'
                                            }`}
                                    />
                                    <Mail className="absolute right-3 top-3.5 w-5 h-5 text-gray-400" />
                                </div>
                            </div>
                        </div>

                        {/* Custom Date Input */}
                        <AnimatePresence>
                            {days === 'custom' && (
                                <motion.div
                                    initial={{ opacity: 0, height: 0 }}
                                    animate={{ opacity: 1, height: 'auto' }}
                                    exit={{ opacity: 0, height: 0 }}
                                    className="space-y-2"
                                >
                                    <label className="flex items-center gap-2 text-sm font-medium text-gray-700">
                                        <Calendar className="w-4 h-4" />
                                        Custom Date
                                    </label>
                                    <input
                                        type="date"
                                        value={customDate}
                                        onChange={(e) => setCustomDate(e.target.value)}
                                        max={new Date().toISOString().split('T')[0]}
                                        className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all"
                                    />
                                </motion.div>
                            )}
                        </AnimatePresence>

                        {/* Error Messages */}
                        <AnimatePresence>
                            {error && (
                                <motion.div
                                    initial={{ opacity: 0, y: -10 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    exit={{ opacity: 0, y: -10 }}
                                    className="flex items-center gap-2 p-4 bg-red-50 border border-red-200 rounded-xl text-red-700"
                                >
                                    <AlertCircle className="w-5 h-5 flex-shrink-0" />
                                    {error}
                                </motion.div>
                            )}
                            {csvError && (
                                <motion.div
                                    initial={{ opacity: 0, y: -10 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    exit={{ opacity: 0, y: -10 }}
                                    className="flex items-center gap-2 p-4 bg-red-50 border border-red-200 rounded-xl text-red-700"
                                >
                                    <AlertCircle className="w-5 h-5 flex-shrink-0" />
                                    {csvError}
                                </motion.div>
                            )}
                        </AnimatePresence>

                        {/* Action Buttons */}
                        <div className="flex flex-wrap gap-3">
                            <motion.button
                                whileHover={{ scale: 1.02 }}
                                whileTap={{ scale: 0.98 }}
                                onClick={handleSubmit}
                                disabled={loading || connectionStatus !== 'connected'}
                                className="flex items-center gap-2 px-6 py-3 bg-gradient-to-r from-blue-500 to-purple-600 text-white rounded-xl font-medium hover:from-blue-600 hover:to-purple-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                            >
                                {loading ? (
                                    <Loader2 className="w-5 h-5 animate-spin" />
                                ) : (
                                    <Play className="w-5 h-5" />
                                )}
                                {loading ? 'Analyzing...' : 'Start Analysis'}
                            </motion.button>

                            <AnimatePresence>
                                {loading && (
                                    <motion.button
                                        initial={{ opacity: 0, scale: 0.8 }}
                                        animate={{ opacity: 1, scale: 1 }}
                                        exit={{ opacity: 0, scale: 0.8 }}
                                        whileHover={{ scale: 1.02 }}
                                        whileTap={{ scale: 0.98 }}
                                        onClick={handleCancel}
                                        className="flex items-center gap-2 px-6 py-3 bg-red-500 text-white rounded-xl font-medium hover:bg-red-600 transition-all"
                                    >
                                        <X className="w-5 h-5" />
                                        Cancel
                                    </motion.button>
                                )}
                            </AnimatePresence>

                            <motion.button
                                whileHover={{ scale: 1.02 }}
                                whileTap={{ scale: 0.98 }}
                                onClick={handleReset}
                                className="flex items-center gap-2 px-6 py-3 bg-gray-100 text-gray-700 rounded-xl font-medium hover:bg-gray-200 transition-all"
                            >
                                <RotateCcw className="w-5 h-5" />
                                Reset
                            </motion.button>
                        </div>
                    </div>
                </motion.div>

                {/* Progress Section */}
                <AnimatePresence>
                    {(loading || progress > 0) && (
                        <motion.div
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: -20 }}
                            className="bg-white rounded-3xl shadow-xl p-8 mb-8 border border-gray-100"
                        >
                            <div className="space-y-4">
                                <div className="flex items-center justify-between">
                                    <h3 className="text-lg font-semibold text-gray-800">Analysis Progress</h3>
                                    <span className="text-sm text-gray-500">{progress}%</span>
                                </div>
                                <div className="w-full bg-gray-200 rounded-full h-3 overflow-hidden">
                                    <motion.div
                                        className="h-full bg-gradient-to-r from-blue-500 to-purple-600 rounded-full"
                                        initial={{ width: 0 }}
                                        animate={{ width: `${progress}%` }}
                                        transition={{ duration: 0.5 }}
                                    />
                                </div>
                                {message && (
                                    <p className="text-gray-600 text-center">{message}</p>
                                )}
                            </div>
                        </motion.div>
                    )}
                </AnimatePresence>

                {/* Results Tabs and Actions */}
                <AnimatePresence>
                    {Object.keys(results).length > 0 && (
                        <motion.div
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            className="bg-white rounded-3xl shadow-xl p-8 mb-8 border border-gray-100"
                        >
                            {/* Action Buttons */}
                            <div className="flex items-center justify-between mb-6">
                                <h3 className="text-xl font-bold text-gray-800">Analysis Results</h3>
                                <div className="flex items-center gap-3">
                                    {/* Download Dropdown */}
                                    <div className="relative download-dropdown">
                                        <motion.button
                                            whileHover={{ scale: 1.02 }}
                                            whileTap={{ scale: 0.98 }}
                                            onClick={() => setShowDownloadDropdown(!showDownloadDropdown)}
                                            className="flex items-center gap-2 px-4 py-2 bg-blue-500 text-white rounded-lg font-medium hover:bg-blue-600 transition-all"
                                        >
                                            <Download className="w-4 h-4" />
                                            Download
                                            <ChevronDown className="w-4 h-4" />
                                        </motion.button>
                                        
                                        <AnimatePresence>
                                            {showDownloadDropdown && (
                                                <motion.div
                                                    initial={{ opacity: 0, y: -10 }}
                                                    animate={{ opacity: 1, y: 0 }}
                                                    exit={{ opacity: 0, y: -10 }}
                                                    className="absolute right-0 top-full mt-2 bg-white border border-gray-200 rounded-lg shadow-lg z-10 min-w-[120px]"
                                                >
                                                    <button
                                                        onClick={() => downloadAllResults('csv')}
                                                        className="w-full px-4 py-2 text-left hover:bg-gray-50 flex items-center gap-2"
                                                    >
                                                        <FileSpreadsheet className="w-4 h-4" />
                                                        CSV
                                                    </button>
                                                    <button
                                                        onClick={() => downloadAllResults('txt')}
                                                        className="w-full px-4 py-2 text-left hover:bg-gray-50 flex items-center gap-2"
                                                    >
                                                        <FileText className="w-4 h-4" />
                                                        TXT
                                                    </button>
                                                    <button
                                                        onClick={() => downloadAllResults('pdf')}
                                                        className="w-full px-4 py-2 text-left hover:bg-gray-50 flex items-center gap-2"
                                                    >
                                                        <FileDown className="w-4 h-4" />
                                                        PDF
                                                    </button>
                                                </motion.div>
                                            )}
                                        </AnimatePresence>
                                    </div>

                                    {/* Email Button */}
                                    <motion.button
                                        whileHover={{ scale: 1.02 }}
                                        whileTap={{ scale: 0.98 }}
                                        onClick={sendEmailResults}
                                        disabled={sendingEmail}
                                        className="flex items-center gap-2 px-4 py-2 bg-green-500 text-white rounded-lg font-medium hover:bg-green-600 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                                    >
                                        {sendingEmail ? (
                                            <Loader2 className="w-4 h-4 animate-spin" />
                                        ) : (
                                            <Send className="w-4 h-4" />
                                        )}
                                        {sendingEmail ? 'Sending...' : 'Send Email'}
                                    </motion.button>
                                </div>
                            </div>

                            {/* Tabs */}
                            <div className="border-b border-gray-200 mb-6">
                                <div className="flex space-x-8 overflow-x-auto">
                                    {urls.map((url, index) => {
                                        const urlResults = results[url];
                                        const hasResults = urlResults && (Array.isArray(urlResults.reviews) ? urlResults.reviews.length > 0 : false) || urlResults?.businessDetails?.name;
                                        
                                        return (
                                            <button
                                                key={index}
                                                onClick={() => setActiveTab(index)}
                                                className={`py-2 px-1 border-b-2 font-medium text-sm whitespace-nowrap ${
                                                    activeTab === index
                                                        ? 'border-blue-500 text-blue-600'
                                                        : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                                                }`}
                                            >
                                                <div className="flex items-center gap-2">
                                                    {hasResults ? (
                                                        <CheckCircle2 className="w-4 h-4 text-green-500" />
                                                    ) : (
                                                        <Loader2 className="w-4 h-4 animate-spin text-blue-500" />
                                                    )}
                                                    Business {index + 1}
                                                </div>
                                            </button>
                                        );
                                    })}
                                </div>
                            </div>

                            {/* Tab Content */}
                            {urls[activeTab] && (
                                <div>
                                    {(() => {
                                        const currentUrl = urls[activeTab];
                                        const urlResults = results[currentUrl];
                                        const stats = getStats(currentUrl);
                                        const businessDetails = urlResults?.businessDetails;
                                        const reviews = Array.isArray(urlResults?.reviews) ? urlResults.reviews : [];
                                        
                                        return (
                                            <>
                                                {/* Stats Grid */}
                                                {stats && (
                                                    <motion.div
                                                        initial={{ opacity: 0, y: 20 }}
                                                        animate={{ opacity: 1, y: 0 }}
                                                        className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8"
                                                    >
                                                        <motion.div
                                                            whileHover={{ scale: 1.02 }}
                                                            className="bg-gray-50 rounded-2xl shadow-lg p-6 border border-gray-100"
                                                        >
                                                            <div className="flex items-center gap-3">
                                                                <div className="p-2 bg-blue-100 rounded-lg">
                                                                    <MessageSquare className="w-5 h-5 text-blue-600" />
                                                                </div>
                                                                <div>
                                                                    <p className="text-2xl font-bold text-gray-800">{stats.totalReviews}</p>
                                                                    <p className="text-sm text-gray-600">Total Reviews</p>
                                                                </div>
                                                            </div>
                                                        </motion.div>

                                                        <motion.div
                                                            whileHover={{ scale: 1.02 }}
                                                            className="bg-gray-50 rounded-2xl shadow-lg p-6 border border-gray-100"
                                                        >
                                                            <div className="flex items-center gap-3">
                                                                <div className="p-2 bg-yellow-100 rounded-lg">
                                                                    <Star className="w-5 h-5 text-yellow-600" />
                                                                </div>
                                                                <div>
                                                                    <p className="text-2xl font-bold text-gray-800">{stats.averageRating}⭐</p>
                                                                    <p className="text-sm text-gray-600">Average Rating</p>
                                                                </div>
                                                            </div>
                                                        </motion.div>

                                                        <motion.div
                                                            whileHover={{ scale: 1.02 }}
                                                            className="bg-gray-50 rounded-2xl shadow-lg p-6 border border-gray-100"
                                                        >
                                                            <div className="flex items-center gap-3">
                                                                <div className="p-2 bg-green-100 rounded-lg">
                                                                    <TrendingUp className="w-5 h-5 text-green-600" />
                                                                </div>
                                                                <div>
                                                                    <p className="text-2xl font-bold text-gray-800">{stats.highRatings}</p>
                                                                    <p className="text-sm text-gray-600">High Ratings (4-5★)</p>
                                                                </div>
                                                            </div>
                                                        </motion.div>

                                                        <motion.div
                                                            whileHover={{ scale: 1.02 }}
                                                            className="bg-gray-50 rounded-2xl shadow-lg p-6 border border-gray-100"
                                                        >
                                                            <div className="flex items-center gap-3">
                                                                <div className="p-2 bg-red-100 rounded-lg">
                                                                    <TrendingDown className="w-5 h-5 text-red-600" />
                                                                </div>
                                                                <div>
                                                                    <p className="text-2xl font-bold text-gray-800">{stats.lowRatings}</p>
                                                                    <p className="text-sm text-gray-600">Low Ratings (1-2★)</p>
                                                                </div>
                                                            </div>
                                                        </motion.div>
                                                    </motion.div>
                                                )}

                                                {/* Business Information */}
                                                {businessDetails && businessDetails.name && (
                                                    <motion.div
                                                        initial={{ opacity: 0, y: 20 }}
                                                        animate={{ opacity: 1, y: 0 }}
                                                        className="bg-gray-50 rounded-3xl shadow-xl p-8 mb-8 border border-gray-100"
                                                    >
                                                        <div className="flex items-center gap-3 mb-6">
                                                            <div className="p-2 bg-blue-100 rounded-lg">
                                                                <Building2 className="w-6 h-6 text-blue-600" />
                                                            </div>
                                                            <h3 className="text-xl font-bold text-gray-800">Business Information</h3>
                                                        </div>

                                                        <div className="grid md:grid-cols-2 gap-6">
                                                            {/* Left Column */}
                                                            <div className="space-y-4">
                                                                {businessDetails.name && (
                                                                    <div className="flex items-start gap-3">
                                                                        <Building2 className="w-5 h-5 text-gray-400 mt-0.5" />
                                                                        <div>
                                                                            <p className="text-sm font-medium text-gray-500">Business Name</p>
                                                                            <p className="text-gray-800 font-semibold">{businessDetails.name}</p>
                                                                        </div>
                                                                    </div>
                                                                )}

                                                                {businessDetails.address && (
                                                                    <div className="flex items-start gap-3">
                                                                        <MapPin className="w-5 h-5 text-gray-400 mt-0.5" />
                                                                        <div>
                                                                            <p className="text-sm font-medium text-gray-500">Address</p>
                                                                            <p className="text-gray-800">{businessDetails.address}</p>
                                                                        </div>
                                                                    </div>
                                                                )}

                                                                {businessDetails.phone && (
                                                                    <div className="flex items-start gap-3">
                                                                        <Phone className="w-5 h-5 text-gray-400 mt-0.5" />
                                                                        <div>
                                                                            <p className="text-sm font-medium text-gray-500">Phone</p>
                                                                            <p className="text-gray-800">{businessDetails.phone}</p>
                                                                        </div>
                                                                    </div>
                                                                )}

                                                                {businessDetails.website && (
                                                                    <div className="flex items-start gap-3">
                                                                        <ExternalLink className="w-5 h-5 text-gray-400 mt-0.5" />
                                                                        <div>
                                                                            <p className="text-sm font-medium text-gray-500">Website</p>
                                                                            <a
                                                                                href={businessDetails.website}
                                                                                target="_blank"
                                                                                rel="noopener noreferrer"
                                                                                className="text-blue-600 hover:text-blue-800 underline"
                                                                            >
                                                                                {businessDetails.website}
                                                                            </a>
                                                                        </div>
                                                                    </div>
                                                                )}
                                                            </div>

                                                            {/* Right Column */}
                                                            <div className="space-y-4">
                                                                {businessDetails.category && (
                                                                    <div className="flex items-start gap-3">
                                                                        <div className="w-5 h-5 bg-purple-100 rounded mt-0.5"></div>
                                                                        <div>
                                                                            <p className="text-sm font-medium text-gray-500">Category</p>
                                                                            <p className="text-gray-800">{businessDetails.category}</p>
                                                                        </div>
                                                                    </div>
                                                                )}

                                                                {businessDetails.rating && (
                                                                    <div className="flex items-start gap-3">
                                                                        <Star className="w-5 h-5 text-yellow-400 mt-0.5" />
                                                                        <div>
                                                                            <p className="text-sm font-medium text-gray-500">Overall Rating</p>
                                                                            <p className="text-gray-800 font-semibold">{businessDetails.rating}⭐</p>
                                                                        </div>
                                                                    </div>
                                                                )}

                                                                {businessDetails.total_reviews && (
                                                                    <div className="flex items-start gap-3">
                                                                        <MessageSquare className="w-5 h-5 text-green-400 mt-0.5" />
                                                                        <div>
                                                                            <p className="text-sm font-medium text-gray-500">Total Reviews</p>
                                                                            <p className="text-gray-800">{businessDetails.total_reviews}</p>
                                                                        </div>
                                                                    </div>
                                                                )}

                                                                {businessDetails.hours && (
                                                                    <div className="flex items-start gap-3">
                                                                        <Clock className="w-5 h-5 text-blue-400 mt-0.5" />
                                                                        <div>
                                                                            <p className="text-sm font-medium text-gray-500">Hours</p>
                                                                            <p className="text-gray-800">{businessDetails.hours}</p>
                                                                        </div>
                                                                    </div>
                                                                )}
                                                            </div>
                                                        </div>
                                                    </motion.div>
                                                )}

                                                {/* Reviews Table */}
                                                {Array.isArray(reviews) && reviews.length > 0 && (
                                                    <motion.div
                                                        initial={{ opacity: 0, y: 20 }}
                                                        animate={{ opacity: 1, y: 0 }}
                                                        className="bg-gray-50 rounded-3xl shadow-xl overflow-hidden border border-gray-100"
                                                    >
                                                        <div className="flex items-center justify-between p-6 border-b border-gray-200">
                                                            <h3 className="text-xl font-bold text-gray-800 flex items-center gap-2">
                                                                <MessageSquare className="w-6 h-6 text-blue-600" />
                                                                Reviews ({reviews.length})
                                                            </h3>
                                                        </div>

                                                        <div className="overflow-x-auto">
                                                            <table className="w-full">
                                                                <thead className="bg-gray-100">
                                                                    <tr>
                                                                        <th className="px-6 py-4 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Date</th>
                                                                        <th className="px-6 py-4 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Author</th>
                                                                        <th className="px-6 py-4 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Rating</th>
                                                                        <th className="px-6 py-4 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Review</th>
                                                                        <th className="px-6 py-4 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Photo</th>
                                                                    </tr>
                                                                </thead>
                                                                <tbody className="divide-y divide-gray-200">
                                                                    {Array.isArray(reviews) ? reviews.map((review, index) => (
                                                                        <motion.tr
                                                                            key={index}
                                                                            variants={slideInVariants}
                                                                            initial="hidden"
                                                                            animate="visible"
                                                                            transition={{ delay: index * 0.1 }}
                                                                            className="hover:bg-gray-100 transition-colors"
                                                                        >
                                                                            <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                                                                                {review.date}
                                                                            </td>
                                                                            <td className="px-6 py-4 whitespace-nowrap">
                                                                                <div className="flex items-center gap-2">
                                                                                    <Users className="w-4 h-4 text-gray-400" />
                                                                                    <span className="font-medium text-gray-800">{review.author}</span>
                                                                                </div>
                                                                            </td>
                                                                            <td className="px-6 py-4 whitespace-nowrap">
                                                                                <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getRatingClass(review.rating)}`}>
                                                                                    {review.rating}⭐
                                                                                </span>
                                                                            </td>
                                                                            <td className="px-6 py-4">
                                                                                <div className="max-w-xs truncate text-sm text-gray-600">
                                                                                    {review.text || 'No text provided'}
                                                                                </div>
                                                                            </td>
                                                                            <td className="px-6 py-4">
                                                                                {Array.isArray(review.photo) && review.photo.length > 0 && (
                                                                                    <div className="flex gap-1">
                                                                                        {review.photo.slice(0, 2).map((url, idx) => (
                                                                                            <img
                                                                                                key={idx}
                                                                                                src={url}
                                                                                                alt={`Review image ${idx + 1}`}
                                                                                                className="w-10 h-10 rounded-lg object-cover"
                                                                                            />
                                                                                        ))}
                                                                                        {review.photo.length > 2 && (
                                                                                            <div className="w-10 h-10 rounded-lg bg-gray-200 flex items-center justify-center text-xs text-gray-500">
                                                                                                +{review.photo.length - 2}
                                                                                            </div>
                                                                                        )}
                                                                                    </div>
                                                                                )}
                                                                                {!Array.isArray(review.photo) || review.photo.length === 0 ? (
                                                                                    <span className="text-gray-400">—</span>
                                                                                ) : null}
                                                                            </td>
                                                                        </motion.tr>
                                                                    )): null}
                                                                </tbody>
                                                            </table>
                                                        </div>
                                                    </motion.div>
                                                )}
                                            </>
                                        );
                                    })()}
                                </div>
                            )}
                        </motion.div>
                    )}
                </AnimatePresence>


            </motion.div>
        </div>
    );
}

export default function WrappedApp() {
    return <ErrorBoundary><App /></ErrorBoundary>;
}