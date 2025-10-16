// New User Dashboard JavaScript
(function() {
    'use strict';
    
    // Global variables
    let userBookings = [];
    let currentUserId = null;
    let currentBookingId = null;
    let selectedRating = 0;
    let socket = null;
    
    // Initialize dashboard
    document.addEventListener('DOMContentLoaded', function() {
        console.log('Initializing new user dashboard...');
        initializeDashboard();
    });
    
    // Initialize dashboard components
    async function initializeDashboard() {
        try {
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
    async function loadDashboardData() {
        try {
            // Show loading state
            showBookingsLoading(true);
            
            // Load bookings
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
    }
    
    // Load user bookings
    async function loadBookings() {
        try {
            const token = localStorage.getItem('token');
            const response = await fetch('/bookings/user', {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            
            if (response.ok) {
                userBookings = await response.json();
                console.log('Bookings loaded:', userBookings);
                renderBookings();
            } else {
                const error = await response.text();
                console.error('Error loading bookings:', response.status, error);
                showNotification('Error loading bookings', 'error');
            }
        } catch (error) {
            console.error('Error loading bookings:', error);
            showNotification('Error loading bookings', 'error');
        }
    }
    
    // Render bookings
    function renderBookings() {
        const container = document.getElementById('bookingsList');
        const emptyState = document.getElementById('emptyState');
        
        if (!userBookings || userBookings.length === 0) {
            container.style.display = 'none';
            emptyState.classList.remove('d-none');
            emptyState.style.display = 'block';
            return;
        }
        
        container.style.display = 'block';
        emptyState.classList.add('d-none');
        emptyState.style.display = 'none';
        
        // Filter bookings based on selected filter
        const filter = document.querySelector('input[name="bookingFilter"]:checked').id;
        let filteredBookings = userBookings;
        
        switch(filter) {
            case 'activeBookings':
                filteredBookings = userBookings.filter(b => ['Pending', 'Accepted', 'In Progress'].includes(b.status));
                break;
            case 'completedBookings':
                filteredBookings = userBookings.filter(b => b.status === 'Completed');
                break;
        }
        
        container.innerHTML = filteredBookings.map(booking => createBookingCard(booking)).join('');
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
                    amount: booking.price * 100, // Convert to paise
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
            document.getElementById('paymentServiceName').textContent = booking.service_name || 'Service';
            document.getElementById('paymentAmount').textContent = `₹${booking.price || 0}`;
            
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
    
    window.refreshDashboard = function() {
        loadDashboardData();
    };
    
    window.logout = async function() {
        try {
            const token = localStorage.getItem('token');
            if (token) {
                await fetch('/logout', {
                    method: 'POST',
                    headers: { 'Authorization': `Bearer ${token}` }
                });
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
            loading.classList.remove('d-none');
            loading.style.display = 'block';
            list.style.display = 'none';
            empty.classList.add('d-none');
            empty.style.display = 'none';
        } else {
            loading.style.display = 'none';
            loading.classList.add('d-none');
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
    
    // Test Razorpay directly
    async function testRazorpayDirect() {
        console.log('Testing Razorpay directly...');
        console.log('Razorpay available:', typeof Razorpay !== 'undefined');
        
        if (typeof Razorpay === 'undefined') {
            showNotification('Razorpay not loaded! Check console for details.', 'error');
            return;
        }
        
        try {
            // Get Razorpay key from server
            const keyResponse = await fetch('/payments/razorpay/get-key');
            const keyData = await keyResponse.json();
            
            const options = {
                key: keyData.key_id, // Use live key from server
                amount: 10000, // ₹100 in paise
                currency: 'INR',
                name: 'Hoofix Test',
                description: 'Direct Razorpay Test',
                order_id: 'test_order_' + Date.now(),
                handler: function(response) {
                    showNotification('✅ Payment successful! ID: ' + response.razorpay_payment_id, 'success');
                },
                modal: {
                    ondismiss: function() {
                        showNotification('⚠️ Payment cancelled', 'warning');
                    }
                },
                theme: {
                    color: '#667eea'
                }
            };
            
            console.log('Opening Razorpay with options:', options);
            const rzp = new Razorpay(options);
            rzp.open();
            
            showNotification('🔄 Opening Razorpay payment window...', 'info');
            
        } catch (error) {
            console.error('Error:', error);
            showNotification('❌ Error: ' + error.message, 'error');
        }
    }
})();

