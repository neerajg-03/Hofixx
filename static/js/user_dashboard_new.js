// New User Dashboard JavaScript
(function() {
    'use strict';
    
    // Global variables
    let userBookings = [];
    let currentUserId = null;
    let currentBookingId = null;
    let selectedRating = 0;
    let socket = null;
    let walletSummary = {
        credits: 0,
        transactions: [],
        referral_code: '',
        referral_bonus_claimed: false,
        referred_by: null,
        pending_referral: null
    };
    
    // Declare function references that will be used by global functions
    let renderWalletModalContent;
    let loadDashboardData;
    
    // Define global functions immediately so they're available for onclick handlers
    // These functions will access the internal functions via closure once they're defined
    window.openWalletModal = function() {
        const modalEl = document.getElementById('walletModal');
        if (!modalEl) {
            console.error('Wallet modal element not found');
            return;
        }
        
        // Check if Bootstrap is loaded
        if (typeof bootstrap === 'undefined' || !bootstrap.Modal) {
            console.error('Bootstrap Modal is not available');
            return;
        }
        
        // If renderWalletModalContent is defined, use it; otherwise, just show the modal
        // The modal content will be populated when the wallet data loads
        if (typeof renderWalletModalContent === 'function') {
            renderWalletModalContent();
        } else {
            // If not ready yet, try to load wallet data first
            console.warn('Wallet modal content renderer not ready yet');
        }
        
        // Show the modal
        const modalInstance = new bootstrap.Modal(modalEl);
        modalInstance.show();
    };
    
    window.refreshDashboard = function() {
        if (typeof loadDashboardData === 'function') {
            loadDashboardData();
        } else {
            console.warn('Dashboard data loader not ready yet, reloading page...');
            // Reload the page as fallback
            window.location.reload();
        }
    };
    
    window.logout = async function() {
        try {
            const token = localStorage.getItem('token');
            if (token) {
                try {
                    await fetch('/logout', {
                        method: 'POST',
                        headers: { 'Authorization': `Bearer ${token}` }
                    });
                } catch (e) {
                    console.warn('Logout API call failed:', e);
                }
            }
            
            // Clear local storage
            localStorage.removeItem('token');
            
            // Redirect to login
            window.location.href = '/login';
        } catch (error) {
            console.error('Error during logout:', error);
            // Still redirect to login even if logout fails
            localStorage.removeItem('token');
            window.location.href = '/login';
        }
    };
    
    // Initialize dashboard
    document.addEventListener('DOMContentLoaded', function() {
        console.log('Initializing new user dashboard...');
        initializeDashboard();
    });
    
    // Initialize dashboard components
    async function initializeDashboard() {
        try {
            // Check for token in URL first (from OAuth redirect)
            const urlParams = new URLSearchParams(window.location.search);
            const urlToken = urlParams.get('token');
            if (urlToken) {
                // Store token in localStorage and clean URL
                localStorage.setItem('token', urlToken);
                window.history.replaceState({}, document.title, window.location.pathname);
            }
            
            // Check authentication
            const token = localStorage.getItem('token');
            if (!token) {
                console.log('No token found, redirecting to login');
                window.location.href = '/login';
                return;
            }
            
            // Parse user info from token
            parseUserInfo(token);
            
            // Load dashboard data
            await loadDashboardData();
            await loadProfileData();
            
            // Setup event listeners
            setupEventListeners();
            
            // Initialize WebSocket connection
            initializeWebSocket();
            
            console.log('Dashboard initialized successfully');
        } catch (error) {
            console.error('Error initializing dashboard:', error);
            showNotification('Error loading dashboard. Please refresh the page.', 'error');
        }
    }
    
    // Parse user info from JWT token
    function parseUserInfo(token) {
        try {
            const payload = JSON.parse(atob(token.split('.')[1]));
            const claims = payload?.sub && typeof payload.sub === 'object' ? payload.sub : (payload?.claims || payload);
            
            currentUserId = claims?.id || claims?.user_id;
            const name = claims?.name || 'User';
            const email = claims?.email || 'user@example.com';
            
            // Update UI
            document.getElementById('userName').textContent = name;
            document.getElementById('userEmail').textContent = email;
            
            // Update avatar
            const initials = encodeURIComponent(name.split(' ').map(p => p[0]).join('').slice(0, 2));
            document.getElementById('userAvatar').src = `https://api.dicebear.com/7.x/avataaars/svg?seed=${initials}&backgroundColor=b6e3f4`;
            
        } catch (error) {
            console.error('Error parsing user info:', error);
        }
    }
    
    // Load all dashboard data
    loadDashboardData = async function() {
        try {
            // Show loading state
            showBookingsLoading(true);
            
            // Load wallet and bookings
            await loadWallet();
            await loadBookings();
            
            // Update statistics
            updateStatistics();
            
            // Hide loading state
            showBookingsLoading(false);
            
        } catch (error) {
            console.error('Error loading dashboard data:', error);
            showBookingsLoading(false);
            showNotification('Error loading data. Please try again.', 'error');
        }
    };

    async function loadProfileData() {
        try {
            const token = localStorage.getItem('token');
            const response = await fetch('/api/user/profile', {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (!response.ok) {
                console.error('Error loading profile:', response.status, await response.text().catch(() => ''));
                return;
            }
            const profile = await response.json();
            console.log('Profile loaded:', profile);
            if (profile.name) {
                document.getElementById('userName').textContent = profile.name;
            }
            if (profile.email) {
                document.getElementById('userEmail').textContent = profile.email;
            }
            if (profile.rating !== undefined && profile.rating !== null) {
                document.getElementById('userRating').textContent = `⭐ ${Number(profile.rating).toFixed(1)}`;
            }
        } catch (error) {
            console.error('Error loading profile data:', error);
        }
    }
    
    // Load user bookings
    async function loadBookings() {
        try {
            const token = localStorage.getItem('token');
            if (!token) {
                console.error('No token found for bookings');
                return;
            }
            const response = await fetch('/bookings/user', {
                headers: { 
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                }
            });
            
            if (response.ok) {
                const data = await response.json();
                console.log('Bookings loaded:', data);
                if (Array.isArray(data)) {
                    userBookings = data;
                } else {
                    console.error('Bookings data is not an array:', data);
                    userBookings = [];
                }
                // Always render after loading (even if empty)
                renderBookings();
            } else {
                const errorText = await response.text().catch(() => 'Unknown error');
                console.error('Error loading bookings:', response.status, errorText);
                if (response.status === 401 || response.status === 403) {
                    showNotification('Authentication failed. Please login again.', 'error');
                    setTimeout(() => window.location.href = '/login', 2000);
                } else {
                    showNotification('Error loading bookings. Please try again.', 'error');
                }
                userBookings = [];
                renderBookings();
            }
        } catch (error) {
            console.error('Error loading bookings:', error);
            showNotification('Error loading bookings. Please check your connection.', 'error');
            userBookings = [];
            renderBookings();
        }
    }
    
    // Render bookings
    function renderBookings() {
        const container = document.getElementById('bookingsList');
        const emptyState = document.getElementById('emptyState');
        const loading = document.getElementById('bookingsLoading');
        
        // Hide loading state
        if (loading) {
            loading.style.display = 'none';
            loading.classList.add('d-none');
        }
        
        if (!userBookings || userBookings.length === 0) {
            if (container) container.style.display = 'none';
            if (emptyState) {
                emptyState.classList.remove('d-none');
                emptyState.style.display = 'block';
            }
            return;
        }
        
        // Filter bookings based on selected filter
        const filterRadio = document.querySelector('input[name="bookingFilter"]:checked');
        const filter = filterRadio ? filterRadio.id : 'filterAllBookings';
        let filteredBookings = userBookings;
        
        switch(filter) {
            case 'filterActiveBookings':
                filteredBookings = userBookings.filter(b => ['Pending', 'Accepted', 'In Progress'].includes(b.status));
                break;
            case 'filterCompletedBookings':
                filteredBookings = userBookings.filter(b => b.status === 'Completed');
                break;
            case 'filterAllBookings':
            default:
                // Show all bookings (no filtering needed)
                filteredBookings = userBookings;
                break;
        }
        
        // Show empty state if filtered results are empty, but we have bookings
        if (filteredBookings.length === 0 && userBookings.length > 0) {
            if (container) container.style.display = 'none';
            if (emptyState) {
                emptyState.classList.remove('d-none');
                emptyState.style.display = 'block';
                // Update empty state message
                const emptyStateText = emptyState.querySelector('h6');
                if (emptyStateText) {
                    emptyStateText.textContent = `No ${filter === 'filterActiveBookings' ? 'active' : 'completed'} bookings found`;
                }
            }
            return;
        }
        
        // Render bookings
        if (container && filteredBookings.length > 0) {
            container.innerHTML = filteredBookings.map(booking => createBookingCard(booking)).join('');
            container.style.display = 'block';
            if (emptyState) {
                emptyState.classList.add('d-none');
                emptyState.style.display = 'none';
            }
        } else {
            if (container) container.style.display = 'none';
            if (emptyState) {
                emptyState.classList.remove('d-none');
                emptyState.style.display = 'block';
            }
        }
    }
    
    // Create booking card HTML
    function createBookingCard(booking) {
        const statusClass = getStatusClass(booking.status);
        const statusIcon = getStatusIcon(booking.status);
        const actions = createBookingActions(booking);
        
        return `
            <div class="booking-card">
                <div class="row align-items-center">
                    <div class="col-md-3">
                        <div class="d-flex align-items-center">
                            <div class="me-3">
                                <i class="fas fa-${getServiceIcon(booking.service_name)} fa-2x text-primary"></i>
                            </div>
                            <div>
                                <h6 class="mb-1">${booking.service_name || 'Service'}</h6>
                                <small class="text-muted">${formatDate(booking.created_at)}</small>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-2">
                        <div class="d-flex align-items-center">
                            <img src="https://api.dicebear.com/7.x/avataaars/svg?seed=${booking.provider_name || 'Provider'}&backgroundColor=ffd93d" 
                                 class="rounded-circle me-2" width="30" height="30" alt="Provider">
                            <div>
                                <div class="small fw-bold">${booking.provider_name || 'Provider'}</div>
                                <div class="small text-muted">⭐ 4.8</div>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-2">
                        <span class="status-badge status-${statusClass}">
                            <i class="fas fa-${statusIcon} me-1"></i>
                            ${booking.status}
                        </span>
                    </div>
                    <div class="col-md-2">
                        <div class="fw-bold text-primary">₹${booking.price || 0}</div>
                    </div>
                    <div class="col-md-3">
                        <div class="d-flex flex-wrap gap-2">
                            ${actions}
                        </div>
                    </div>
                </div>
            </div>
        `;
    }
    
    // Create booking actions
    function createBookingActions(booking) {
        let actions = [];
        
        // View details button
        actions.push(`
            <button class="action-btn btn-primary" onclick="viewBooking('${booking.id}')" title="View Details">
                <i class="fas fa-eye"></i>
            </button>
        `);
        
        // Track provider button
        if (['In Progress', 'Accepted'].includes(booking.status)) {
            actions.push(`
                <button class="action-btn btn-info" onclick="trackProvider('${booking.id}')" title="Track Provider">
                    <i class="fas fa-map-marker-alt"></i>
                </button>
            `);
        }
        
        // Rate service button
        if (booking.status === 'Completed' && !booking.rating) {
            actions.push(`
                <button class="action-btn btn-warning" onclick="rateBooking('${booking.id}')" title="Rate Service">
                    <i class="fas fa-star"></i>
                </button>
            `);
        }
        
        // Show rating if already rated
        if (booking.status === 'Completed' && booking.rating) {
            actions.push(`
                <span class="badge bg-success">Rated ${booking.rating}/5</span>
            `);
        }
        
        // Payment button
        if (booking.status === 'Completed' && booking.rating && !booking.has_payment) {
            actions.push(`
                <button class="action-btn btn-success" onclick="makePayment('${booking.id}')" title="Make Payment">
                    <i class="fas fa-credit-card"></i>
                </button>
            `);
        }
        
        // Show payment status if paid
        if (booking.status === 'Completed' && booking.has_payment) {
            const paymentClass = booking.payment_status === 'Success' ? 'success' : 'warning';
            actions.push(`
                <span class="badge bg-${paymentClass}">${booking.payment_status}</span>
            `);
        }
        
        // View completion button
        if (booking.status === 'Completed') {
            actions.push(`
                <button class="action-btn btn-info" onclick="viewCompletion('${booking.id}')" title="View Completion">
                    <i class="fas fa-check-circle"></i>
                </button>
            `);
        }
        
        return actions.join('');
    }
    
    async function loadWallet() {
        try {
            const token = localStorage.getItem('token');
            if (!token) {
                console.error('No token found for wallet');
                return;
            }
            const response = await fetch('/api/wallet', {
                headers: { 
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                }
            });
            if (!response.ok) {
                const errorText = await response.text().catch(() => 'Unknown error');
                console.error('Error loading wallet:', response.status, errorText);
                if (response.status === 401 || response.status === 403) {
                    console.warn('Authentication failed for wallet');
                    return;
                }
                const error = await response.json().catch(() => ({ error: 'Failed to load wallet' }));
                throw new Error(error.error || 'Failed to load wallet');
            }
            walletSummary = await response.json();
            console.log('Wallet loaded:', walletSummary);
            updateWalletBadge();
            renderWalletModalContent();
        } catch (error) {
            console.error('Error loading wallet:', error);
            // Don't show notification if it's just an auth issue (already handled)
            if (!error.message.includes('401') && !error.message.includes('403')) {
                showNotification('Unable to load wallet details.', 'error');
            }
        }
    }

    function updateWalletBadge() {
        const badge = document.getElementById('walletCredits');
        if (badge) {
            const amount = Number(walletSummary.credits || 0).toFixed(2);
            badge.textContent = `₹${amount} Credits`;
        }
    }

    function renderWalletTransactions() {
        const list = document.getElementById('walletTransactionsList');
        if (!list) return;

        if (!walletSummary.transactions || walletSummary.transactions.length === 0) {
            list.innerHTML = `
                <div class="text-center text-muted small py-3">
                    <i class="fas fa-wallet fa-2x mb-2"></i>
                    <div>No transactions yet.</div>
                </div>
            `;
            return;
        }

        list.innerHTML = walletSummary.transactions.map(tx => {
            const sign = tx.transaction_type === 'credit' ? '+' : '-';
            const amountClass = tx.transaction_type === 'credit' ? 'text-success' : 'text-danger';
            const date = tx.created_at ? new Date(tx.created_at).toLocaleString() : '';
            return `
                <div class="transaction-item">
                    <div>
                        <div class="fw-semibold">${tx.description || tx.source}</div>
                        <div class="small text-muted">${date}</div>
                    </div>
                    <div class="text-end">
                        <div class="fw-bold ${amountClass}">${sign}₹${Number(tx.amount || 0).toFixed(2)}</div>
                        <div class="small text-muted">Balance: ₹${Number(tx.balance_after || 0).toFixed(2)}</div>
                    </div>
                </div>
            `;
        }).join('');
    }

    renderWalletModalContent = function() {
        const balanceEl = document.getElementById('walletBalanceValue');
        if (balanceEl) {
            balanceEl.textContent = `₹${Number(walletSummary.credits || 0).toFixed(2)}`;
        }

        const referralCodeValue = document.getElementById('referralCodeValue');
        if (referralCodeValue) {
            referralCodeValue.value = walletSummary.referral_code || 'Not available';
        }

        const referralStatus = document.getElementById('referralStatusText');
        const infoMessage = document.getElementById('walletInfoMessage');
        const referralForm = document.getElementById('walletReferralForm');
        const referralCodeInput = document.getElementById('referralCodeInput');
        if (referralStatus) {
            referralStatus.classList.remove('text-success', 'text-warning');
            if (walletSummary.referral_bonus_claimed) {
                referralStatus.textContent = 'Referral bonus already credited to your wallet.';
                referralStatus.classList.add('text-success');
            } else if (walletSummary.pending_referral) {
                referralStatus.textContent = 'Referral request pending admin approval.';
                referralStatus.classList.add('text-warning');
            } else if (walletSummary.referred_by) {
                referralStatus.textContent = 'Referral applied from a friend.';
            } else {
                referralStatus.textContent = 'Share your referral code and both of you earn bonus credits!';
            }
        }
        if (infoMessage) {
            infoMessage.classList.remove('alert-success', 'alert-warning');
            if (walletSummary.pending_referral) {
                infoMessage.textContent = 'Referral request submitted. Admin review pending.';
                infoMessage.classList.add('alert-warning');
            } else if (walletSummary.referral_bonus_claimed) {
                infoMessage.textContent = 'You have already received your referral bonus. Invite more friends to earn rewards.';
                infoMessage.classList.add('alert-success');
            } else {
                infoMessage.textContent = 'Earn bonus credits by sharing your referral code with friends.';
            }
        }
        if (referralForm) {
            const disableReferral = walletSummary.referral_bonus_claimed || !!walletSummary.pending_referral;
            Array.from(referralForm.elements).forEach(el => el.disabled = disableReferral && el.id !== 'referralCodeInput');
            if (referralCodeInput) {
                referralCodeInput.disabled = walletSummary.referral_bonus_claimed || !!walletSummary.pending_referral || !!walletSummary.referred_by;
            }
        }

        renderWalletTransactions();
    };

    // openWalletModal is now defined at the top as a global function

    async function handleWalletTopup(event) {
        event.preventDefault();
        const amountField = document.getElementById('walletTopupAmount');
        const amount = parseFloat(amountField.value);
        if (isNaN(amount) || amount <= 0) {
            showNotification('Enter a valid amount to add.', 'error');
            return;
        }

        try {
            const token = localStorage.getItem('token');
            const createResponse = await fetch('/api/wallet/razorpay/create-order', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({ amount })
            });
            const orderData = await createResponse.json();
            if (!createResponse.ok) {
                const errorMsg = orderData.error || 'Failed to initiate payment';
                const errorDetails = orderData.details ? ` ${orderData.details}` : '';
                throw new Error(errorMsg + errorDetails);
            }

            const options = {
                key: orderData.key_id,
                amount: orderData.amount,
                currency: orderData.currency,
                name: 'Hofix Wallet',
                description: 'Wallet top-up',
                order_id: orderData.order_id,
                handler: async function (response) {
                    try {
                        const verifyResponse = await fetch('/api/wallet/razorpay/verify', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'Authorization': `Bearer ${token}`
                            },
                            body: JSON.stringify(response)
                        });
                        const verifyData = await verifyResponse.json();
                        if (!verifyResponse.ok) {
                            throw new Error(verifyData.error || 'Payment verification failed');
                        }
                        showNotification('Payment successful! Wallet updated.', 'success');
                        amountField.value = '';
                        await loadWallet();
                    } catch (error) {
                        console.error('Wallet verification error:', error);
                        showNotification(error.message || 'Failed to verify payment', 'error');
                    }
                },
                prefill: {
                    email: document.getElementById('userEmail')?.textContent || '',
                    name: document.getElementById('userName')?.textContent || ''
                },
                theme: {
                    color: '#0d6efd'
                }
            };

            const rzp = new Razorpay(options);
            rzp.on('payment.failed', function (response) {
                console.error('Razorpay payment failed:', response);
                showNotification(response.error?.description || 'Payment was cancelled', 'error');
            });
            rzp.open();
        } catch (error) {
            console.error('Wallet top-up error:', error);
            showNotification(error.message || 'Failed to initiate payment', 'error');
        }
    }

    async function handleReferralRedeem(event) {
        event.preventDefault();
        const codeInput = document.getElementById('referralCodeInput');
        const code = (codeInput.value || '').trim();
        if (!code) {
            showNotification('Enter a referral code to redeem bonus.', 'error');
            return;
        }

        try {
            const token = localStorage.getItem('token');
            const response = await fetch('/api/wallet/apply-referral', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({ referral_code: code })
            });
            const result = await response.json();
            if (!response.ok) {
                throw new Error(result.error || 'Failed to redeem referral code');
            }
            showNotification('Referral bonus added to your wallet!', 'success');
            codeInput.value = '';
            await loadWallet();
        } catch (error) {
            console.error('Referral redeem error:', error);
            showNotification(error.message || 'Failed to redeem referral code', 'error');
        }
    }

    function copyReferralCode() {
        const referralInput = document.getElementById('referralCodeValue');
        if (!referralInput || !referralInput.value) return;

        const code = referralInput.value;
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(code)
                .then(() => showNotification('Referral code copied to clipboard!', 'success'))
                .catch(() => fallbackCopy(referralInput, code));
        } else {
            fallbackCopy(referralInput, code);
        }
    }

    function fallbackCopy(inputElement, code) {
        inputElement.select();
        inputElement.setSelectionRange(0, code.length);
        document.execCommand('copy');
        showNotification('Referral code copied to clipboard!', 'success');
    }

    // Update statistics
    function updateStatistics() {
        const totalBookings = userBookings.length;
        const activeBookings = userBookings.filter(b => ['Pending', 'Accepted', 'In Progress'].includes(b.status)).length;
        const completedBookings = userBookings.filter(b => b.status === 'Completed').length;
        const totalSpent = userBookings
            .filter(b => b.status === 'Completed' && b.has_payment)
            .reduce((sum, b) => sum + (b.price || 0), 0);
        
        document.getElementById('totalBookings').textContent = totalBookings;
        document.getElementById('activeBookings').textContent = activeBookings;
        document.getElementById('completedBookings').textContent = completedBookings;
        document.getElementById('totalSpent').textContent = `₹${totalSpent}`;
    }
    
    // Initialize WebSocket connection
    function initializeWebSocket() {
        try {
            socket = io();
            
            socket.on('connect', function() {
                console.log('Connected to WebSocket server');
                showNotification('Connected to real-time updates', 'info');
            });
            
            socket.on('disconnect', function() {
                console.log('Disconnected from WebSocket server');
                showNotification('Disconnected from real-time updates', 'warning');
            });
            
            socket.on('booking_status', function(data) {
                console.log('Received booking status update:', data);
                handleBookingStatusUpdate(data);
            });
            
            socket.on('notification', function(data) {
                console.log('Received notification:', data);
                showNotification(data.message, data.type || 'info');
            });
            
        } catch (error) {
            console.error('Error initializing WebSocket:', error);
        }
    }
    
    // Handle booking status updates
    function handleBookingStatusUpdate(data) {
        // Find and update the booking in our local array
        const bookingIndex = userBookings.findIndex(b => b.id === data.id);
        if (bookingIndex !== -1) {
            userBookings[bookingIndex] = { ...userBookings[bookingIndex], ...data };
            renderBookings();
            updateStatistics();
            showNotification(`Booking status updated: ${data.status}`, 'info');
        }
    }
    
    // Setup event listeners
    function setupEventListeners() {
        // Booking filter change
        document.querySelectorAll('input[name="bookingFilter"]').forEach(radio => {
            radio.addEventListener('change', renderBookings);
        });

        const walletBadge = document.getElementById('walletCredits');
        if (walletBadge) {
            walletBadge.addEventListener('click', openWalletModal);
        }

        const walletTopupForm = document.getElementById('walletTopupForm');
        if (walletTopupForm) {
            walletTopupForm.addEventListener('submit', handleWalletTopup);
        }

        const referralForm = document.getElementById('walletReferralForm');
        if (referralForm) {
            referralForm.addEventListener('submit', handleReferralRedeem);
        }

        const copyReferralBtn = document.getElementById('copyReferralCode');
        if (copyReferralBtn) {
            copyReferralBtn.addEventListener('click', copyReferralCode);
        }

        const refreshWalletBtn = document.getElementById('refreshWalletTransactions');
        if (refreshWalletBtn) {
            refreshWalletBtn.addEventListener('click', async () => {
                await loadWallet();
                showNotification('Wallet refreshed', 'info');
            });
        }
        
        // Rating modal events
        setupRatingModal();
        
        // Payment modal events
        setupPaymentModal();
    }
    
    // Setup rating modal
    function setupRatingModal() {
        const modal = document.getElementById('ratingModal');
        const stars = modal.querySelectorAll('.star');
        const submitBtn = document.getElementById('submitRating');
        
        // Star click events
        stars.forEach(star => {
            star.addEventListener('click', function() {
                selectedRating = parseInt(this.dataset.rating);
                updateStarDisplay(stars, selectedRating);
                submitBtn.disabled = false;
            });
            
            star.addEventListener('mouseenter', function() {
                const rating = parseInt(this.dataset.rating);
                updateStarDisplay(stars, rating);
            });
        });
        
        // Submit rating
        submitBtn.addEventListener('click', submitRating);
    }
    
    // Update star display
    function updateStarDisplay(stars, rating) {
        stars.forEach((star, index) => {
            if (index < rating) {
                star.className = 'fas fa-star star active';
            } else {
                star.className = 'far fa-star star';
            }
        });
    }
    
    // Submit rating
    async function submitRating() {
        if (selectedRating === 0) return;
        
        try {
            const token = localStorage.getItem('token');
            const review = document.getElementById('reviewText').value;
            
            const response = await fetch(`/bookings/${currentBookingId}/rate`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({
                    rating: selectedRating,
                    review: review
                })
            });
            
            if (response.ok) {
                showNotification('Thank you for your rating!', 'success');
                bootstrap.Modal.getInstance(document.getElementById('ratingModal')).hide();
                
                // Refresh dashboard
                await loadDashboardData();
            } else {
                const error = await response.text();
                showNotification('Failed to submit rating', 'error');
            }
        } catch (error) {
            console.error('Error submitting rating:', error);
            showNotification('Failed to submit rating', 'error');
        }
    }
    
    // Setup payment modal
    function setupPaymentModal() {
        const modal = document.getElementById('paymentModal');
        const proceedBtn = document.getElementById('proceedPayment');
        const walletBtn = document.getElementById('payWithWalletBtn');
        
        console.log('Setting up payment modal...');
        console.log('Modal found:', !!modal);
        console.log('Proceed button found:', !!proceedBtn);
        
        if (proceedBtn) {
            proceedBtn.addEventListener('click', function(e) {
                console.log('Payment button clicked!');
                e.preventDefault();
                processPayment();
            });
        } else {
            console.error('Proceed payment button not found!');
        }

        if (walletBtn) {
            walletBtn.addEventListener('click', async function(e) {
                e.preventDefault();
                await processWalletPayment(this);
            });
        }
    }
    
    // Process payment
    async function processPayment() {
        try {
            console.log('Processing payment...');
            console.log('Razorpay available:', typeof Razorpay !== 'undefined');
            const booking = userBookings.find(b => b.id === currentBookingId);
            if (!booking) {
                console.error('Booking not found:', currentBookingId);
                showNotification('Booking not found', 'error');
                return;
            }
            
            console.log('Booking found:', booking);
            const bookingAmount = Number(booking.price || 0);
            if (!bookingAmount || bookingAmount <= 0) {
                showNotification('Invalid booking amount', 'error');
                return;
            }

            const token = localStorage.getItem('token');
            if (!token) {
                console.error('No token found');
                showNotification('Please login first', 'error');
                return;
            }
            
            console.log('Creating Razorpay order...');
            // Create Razorpay order
            const response = await fetch('/payments/razorpay/create-order', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({
                    amount: Math.round(bookingAmount * 100), // Convert to paise
                    currency: 'INR',
                    booking_id: booking.id
                })
            });
            
            console.log('Response status:', response.status);
            
            if (response.ok) {
                const orderData = await response.json();
                console.log('Order created:', orderData);
                
                // Check if Razorpay is loaded
                if (typeof Razorpay === 'undefined') {
                    console.error('Razorpay not loaded');
                    showNotification('Payment system not loaded. Please refresh the page.', 'error');
                    return;
                }
                
                // Open Razorpay checkout
                const options = {
                    key: orderData.key_id, // Use key from server
                    amount: orderData.amount,
                    currency: orderData.currency,
                    name: 'Hoofix',
                    description: `Payment for ${booking.service_name}`,
                    order_id: orderData.id,
                    handler: function(response) {
                        verifyPayment(response);
                    },
                    prefill: {
                        name: document.getElementById('userName').textContent,
                        email: document.getElementById('userEmail').textContent
                    },
                    theme: {
                        color: '#667eea'
                    },
                    modal: {
                        ondismiss: function() {
                            showNotification('Payment cancelled', 'warning');
                        }
                    }
                };
                
                // For testing - show order data
                console.log('Opening Razorpay with options:', options);
                
                const rzp = new Razorpay(options);
                rzp.open();
                
                bootstrap.Modal.getInstance(document.getElementById('paymentModal')).hide();
            } else {
                const error = await response.text();
                console.error('Payment API error:', response.status, error);
                showNotification(`Payment failed: ${response.status} - ${error}`, 'error');
            }
        } catch (error) {
            console.error('Error processing payment:', error);
            showNotification('Failed to process payment', 'error');
        }
    }

    // Process payment via wallet
    async function processWalletPayment(buttonEl) {
        try {
            const booking = userBookings.find(b => b.id === currentBookingId);
            if (!booking) {
                showNotification('Booking not found', 'error');
                return;
            }

            const bookingAmount = Number(booking.price || 0);
            if (!bookingAmount || bookingAmount <= 0) {
                showNotification('Invalid booking amount', 'error');
                return;
            }

            const walletBalance = Number(walletSummary?.credits || 0);
            if (walletBalance < bookingAmount) {
                showNotification('Insufficient wallet balance', 'error');
                return;
            }

            const token = localStorage.getItem('token');
            if (!token) {
                showNotification('Please login first', 'error');
                return;
            }

            if (buttonEl) {
                buttonEl.disabled = true;
                const originalText = buttonEl.innerHTML;
                buttonEl.setAttribute('data-original-text', originalText);
                buttonEl.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Processing...';
            }

            const response = await fetch('/payments/wallet/pay', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({
                    booking_id: booking.id,
                    amount: bookingAmount
                })
            });

            const result = await response.json().catch(() => ({}));

            if (response.ok) {
                showNotification(result.message || 'Payment completed using wallet', 'success');
                const paymentModalEl = document.getElementById('paymentModal');
                const modalInstance = bootstrap.Modal.getInstance(paymentModalEl);
                if (modalInstance) {
                    modalInstance.hide();
                }
                await loadDashboardData();
            } else {
                showNotification(result.error || 'Failed to complete wallet payment', 'error');
            }

            if (buttonEl) {
                buttonEl.disabled = false;
                buttonEl.innerHTML = buttonEl.getAttribute('data-original-text') || '<i class="fas fa-wallet me-2"></i>Pay with Wallet';
                buttonEl.removeAttribute('data-original-text');
            }
        } catch (error) {
            console.error('Error processing wallet payment:', error);
            showNotification('Failed to complete wallet payment', 'error');
            if (buttonEl) {
                buttonEl.disabled = false;
                buttonEl.innerHTML = buttonEl.getAttribute('data-original-text') || '<i class="fas fa-wallet me-2"></i>Pay with Wallet';
                buttonEl.removeAttribute('data-original-text');
            }
        }
    }
    
    // Verify payment
    async function verifyPayment(paymentResponse) {
        try {
            const token = localStorage.getItem('token');
            
            const response = await fetch('/payments/razorpay/verify', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({
                    razorpay_payment_id: paymentResponse.razorpay_payment_id,
                    razorpay_order_id: paymentResponse.razorpay_order_id,
                    razorpay_signature: paymentResponse.razorpay_signature,
                    booking_id: currentBookingId
                })
            });
            
            if (response.ok) {
                showNotification('Payment successful!', 'success');
                await loadDashboardData();
            } else {
                const error = await response.text();
                showNotification('Payment verification failed', 'error');
            }
        } catch (error) {
            console.error('Error verifying payment:', error);
            showNotification('Payment verification failed', 'error');
        }
    }
    
    // Global functions
    window.rateBooking = function(bookingId) {
        currentBookingId = bookingId;
        const booking = userBookings.find(b => b.id === bookingId);
        
        if (booking) {
            document.getElementById('ratingServiceName').textContent = booking.service_name || 'Service';
            document.getElementById('reviewText').value = '';
            selectedRating = 0;
            document.getElementById('submitRating').disabled = true;
            
            // Reset stars
            const stars = document.querySelectorAll('#ratingStars .star');
            stars.forEach(star => star.className = 'far fa-star star');
            
            new bootstrap.Modal(document.getElementById('ratingModal')).show();
        }
    };
    
    window.makePayment = function(bookingId) {
        currentBookingId = bookingId;
        const booking = userBookings.find(b => b.id === bookingId);
        
        if (booking) {
            if (booking.has_payment) {
                showNotification('Payment is already completed for this booking.', 'info');
                return;
            }
            const bookingAmount = Number(booking.price || 0);
            document.getElementById('paymentServiceName').textContent = booking.service_name || 'Service';
            document.getElementById('paymentAmount').textContent = `₹${bookingAmount.toFixed(2)}`;

            const walletBalance = Number(walletSummary?.credits || 0);
            const walletInfo = document.getElementById('walletPaymentInfo');
            const walletWarning = document.getElementById('walletInsufficientInfo');
            const walletBalanceEl = document.getElementById('walletBalanceForPayment');
            const walletBtn = document.getElementById('payWithWalletBtn');

            if (walletBalanceEl) {
                walletBalanceEl.textContent = `₹${walletBalance.toFixed(2)}`;
            }

            if (walletBalance >= bookingAmount && bookingAmount > 0) {
                if (walletInfo) walletInfo.classList.remove('d-none');
                if (walletWarning) walletWarning.classList.add('d-none');
                if (walletBtn) {
                    walletBtn.classList.remove('d-none');
                    walletBtn.disabled = false;
                    walletBtn.innerHTML = '<i class="fas fa-wallet me-2"></i>Pay with Wallet';
                }
            } else {
                if (walletInfo) walletInfo.classList.add('d-none');
                if (walletWarning) {
                    walletWarning.classList.remove('d-none');
                    walletWarning.innerHTML = `
                        <i class="fas fa-exclamation-triangle me-2"></i>
                        Wallet balance is ₹${walletBalance.toFixed(2)}. You need ₹${Math.max(bookingAmount - walletBalance, 0).toFixed(2)} more to pay with wallet.
                    `;
                }
                if (walletBtn) {
                    walletBtn.classList.add('d-none');
                    walletBtn.disabled = true;
                }
            }
            
            new bootstrap.Modal(document.getElementById('paymentModal')).show();
        }
    };
    
    window.viewBooking = function(bookingId) {
        const booking = userBookings.find(b => b.id === bookingId);
        if (booking) {
            showNotification(`Viewing booking: ${booking.service_name}`, 'info');
            // Implement booking details view
        }
    };
    
    window.trackProvider = function(bookingId) {
        const booking = userBookings.find(b => b.id === bookingId);
        if (booking) {
            // Get user's current location for better tracking
            if (navigator.geolocation) {
                navigator.geolocation.getCurrentPosition(position => {
                    const userLat = position.coords.latitude;
                    const userLon = position.coords.longitude;
                    window.open(`/track-provider?provider_id=${booking.provider_id}&booking_id=${bookingId}&user_lat=${userLat}&user_lon=${userLon}`, '_blank');
                }, error => {
                    console.error('Geolocation error:', error);
                    window.open(`/track-provider?provider_id=${booking.provider_id}&booking_id=${bookingId}`, '_blank');
                });
            } else {
                window.open(`/track-provider?provider_id=${booking.provider_id}&booking_id=${bookingId}`, '_blank');
            }
        }
    };
    
    window.viewCompletion = async function(bookingId) {
        try {
            const token = localStorage.getItem('token');
            const response = await fetch(`/completion/${bookingId}`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            
            if (response.ok) {
                const completion = await response.json();
                showCompletionDetails(completion);
            } else {
                showNotification('Failed to load completion details', 'error');
            }
        } catch (error) {
            console.error('Error loading completion details:', error);
            showNotification('Failed to load completion details', 'error');
        }
    };
    
    // refreshDashboard and logout are already defined at the top as global functions
    // Show completion details
    function showCompletionDetails(completion) {
        const content = document.getElementById('completionContent');
        content.innerHTML = `
            <div class="row">
                <div class="col-md-6">
                    <h6>Completion Notes</h6>
                    <p class="text-muted">${completion.completion_notes || 'No notes provided'}</p>
                </div>
                <div class="col-md-6">
                    <h6>Completed At</h6>
                    <p class="text-muted">${formatDate(completion.completed_at)}</p>
                </div>
            </div>
            ${completion.images && completion.images.length > 0 ? `
                <div class="mt-4">
                    <h6>Completion Images</h6>
                    <div class="row">
                        ${completion.images.map(img => `
                            <div class="col-md-4 mb-3">
                                <img src="${img}" class="img-fluid rounded" alt="Completion image">
                            </div>
                        `).join('')}
                    </div>
                </div>
            ` : ''}
        `;
        
        new bootstrap.Modal(document.getElementById('completionModal')).show();
    }
    
    // Utility functions
    function getStatusClass(status) {
        const statusMap = {
            'Pending': 'pending',
            'Accepted': 'accepted',
            'In Progress': 'in-progress',
            'Completed': 'completed',
            'Cancelled': 'cancelled',
            'Rejected': 'cancelled'
        };
        return statusMap[status] || 'pending';
    }
    
    function getStatusIcon(status) {
        const iconMap = {
            'Pending': 'clock',
            'Accepted': 'check',
            'In Progress': 'cog',
            'Completed': 'check-circle',
            'Cancelled': 'times',
            'Rejected': 'times'
        };
        return iconMap[status] || 'clock';
    }
    
    function getServiceIcon(serviceName) {
        const iconMap = {
            'Electrician': 'bolt',
            'Plumber': 'wrench',
            'Carpenter': 'hammer',
            'Cleaner': 'broom',
            'Painter': 'paint-brush',
            'AC Repair': 'snowflake'
        };
        return iconMap[serviceName] || 'tools';
    }
    
    function formatDate(dateString) {
        if (!dateString) return 'N/A';
        const date = new Date(dateString);
        return date.toLocaleDateString('en-IN', {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    }
    
    function showBookingsLoading(show) {
        const loading = document.getElementById('bookingsLoading');
        const list = document.getElementById('bookingsList');
        const empty = document.getElementById('emptyState');
        
        if (show) {
            if (loading) {
                loading.classList.remove('d-none');
                loading.style.display = 'block';
            }
            if (list) list.style.display = 'none';
            if (empty) {
                empty.classList.add('d-none');
                empty.style.display = 'none';
            }
        } else {
            if (loading) {
                loading.style.display = 'none';
                loading.classList.add('d-none');
            }
        }
    }
    
    function showNotification(message, type) {
        const notification = document.createElement('div');
        notification.className = `notification ${type}`;
        notification.textContent = message;
        
        document.body.appendChild(notification);
        
        // Show notification
        setTimeout(() => notification.classList.add('show'), 100);
        
        // Hide notification
        setTimeout(() => {
            notification.classList.remove('show');
            setTimeout(() => notification.remove(), 300);
        }, 3000);
    }
    
    // User feedback form submission
    const userFeedbackForm = document.getElementById('userFeedbackForm');
    if (userFeedbackForm) {
        userFeedbackForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            
            const formData = {
                name: user.name || 'User',
                email: user.email,
                title: document.getElementById('userFeedbackTitle').value,
                rating: document.querySelector('input[name="userRating"]:checked').value,
                message: document.getElementById('userFeedbackMessage').value
            };
            
            try {
                const response = await fetch('/api/feedback/submit', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${localStorage.getItem('token')}`
                    },
                    body: JSON.stringify(formData)
                });
                
                const result = await response.json();
                
                if (response.ok) {
                    showNotification('Thank you for your feedback! Your review has been submitted.', 'success');
                    userFeedbackForm.reset();
                } else {
                    showNotification(result.error || 'Failed to submit feedback', 'error');
                }
            } catch (error) {
                console.error('Error submitting feedback:', error);
                showNotification('Failed to submit feedback. Please try again.', 'error');
            }
        });
    }
    
})();

