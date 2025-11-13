(function(){
  const token = localStorage.getItem('token') || '';
  if (!token) return;

  // Join provider room to receive booking notifications
  let socket = null;
  try {
    const payload = JSON.parse(atob(token.split('.')[1]));
    const claims = payload?.sub && typeof payload.sub === 'object' ? payload.sub : (payload?.claims || payload);
    const userId = claims?.id || claims?.user_id || claims?.sub || '';
    const role = claims?.role || '';
    if (role === 'provider' && window.io){
      socket = io();
      
      // Join provider-specific room
      socket.emit('join_provider_room', { provider_id: userId });
      console.log(`=== PROVIDER JOINING SOCKET ROOM ===`);
      console.log(`Provider ID: ${userId}`);
      console.log(`Room: provider_${userId}`);
      console.log(`Socket connected: ${socket.connected}`);
      
      // Listen for specific booking assignments
      socket.on('booking_created', (b) => {
        console.log('Received booking_created event:', b);
        renderIncoming([b].concat(incoming));
        showNotification('New booking assigned to you!', 'success');
      });
      
      // Listen for available bookings (when no specific provider is assigned)
      socket.on('new_booking_available', (data) => {
        console.log('Received new_booking_available event:', data);
        showNotification(`New ${data.service_name} booking available nearby!`, 'info');
        // You could show a modal here to let providers claim the booking
        if (confirm(`New ${data.service_name} booking available nearby! Would you like to view it?`)) {
          // Redirect to booking details or show modal
          console.log('Available booking:', data.booking);
        }
      });
      
      socket.on('booking_status', (b) => {
        // Update booking status in real-time
        updateBookingStatus(b.id, b.status);
      });
      
      // Listen for rating events
      socket.on('booking_rated', (data) => {
        console.log('Received booking_rated event:', data);
        showNotification(`${data.user_name} rated your service ${data.rating}/5 stars!`, 'success');
        loadProviderBookings(); // Refresh bookings to show rating
      });
      
      // Listen for booking status updates
      socket.on('booking_status_updated', (data) => {
        console.log('Received booking_status_updated event:', data);
        showNotification(`Booking status updated to ${data.status}`, 'info');
        loadProviderBookings(); // Refresh bookings
      });

      // Listen for new chat messages from track provider page
      socket.on('new_message', (data) => {
        console.log('=== PROVIDER RECEIVED NEW MESSAGE ===');
        console.log('Message data:', data);
        console.log('Booking ID:', data.booking_id);
        console.log('Sender:', data.sender_name);
        console.log('Message:', data.message);
        showNotification(`New message from ${data.sender_name}: ${data.message}`, 'info');
        // Refresh the incoming requests to show the new message
        loadProviderBookings();
      });
    }
  } catch(e) {
    console.error('Error setting up socket connection:', e);
  }

  const incomingEl = document.getElementById('incomingList');
  let incoming = [];
  let hasActiveChats = false;

  function toast(msg){
    try { new bootstrap.Toast(Object.assign(document.createElement('div'), { className: 'toast align-items-center text-bg-primary border-0', role: 'alert', innerHTML: `<div class="d-flex"><div class="toast-body">${msg}</div><button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button></div>`})).show(); } catch(e) { alert(msg); }
  }

  // Load chat messages from active bookings
  async function loadChatMessages() {
    try {
      const token = localStorage.getItem('token');
      if (!token) return;

      const response = await fetch('/bookings/provider', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (response.ok) {
        const bookings = await response.json();
        const activeBookings = bookings.filter(b => ['Accepted', 'In Progress'].includes(b.status));
        
        hasActiveChats = false;
        
        for (const booking of activeBookings) {
          // Get latest chat messages for this booking
          const chatResponse = await fetch(`/api/chat/${booking.id}/messages`, {
            headers: { 'Authorization': `Bearer ${token}` }
          });
          
          if (chatResponse.ok) {
            const chatData = await chatResponse.json();
            const messages = chatData.messages || [];
            
            if (messages.length > 0) {
              hasActiveChats = true;
              displayChatMessage(booking, messages[messages.length - 1]);
            }
          }
        }
      }
    } catch (error) {
      console.error('Error loading chat messages:', error);
    }
  }

  // Display chat message in incoming requests
  function displayChatMessage(booking, lastMessage) {
    const chatCard = document.createElement('div');
    chatCard.className = 'chat-card p-3 rounded-3 border border-info hover-lift';
    chatCard.innerHTML = `
      <div class="d-flex align-items-start">
        <div class="chat-avatar me-3">
          <div class="avatar-circle bg-primary text-white d-flex align-items-center justify-content-center rounded-circle" style="width: 40px; height: 40px;">
            <i class="fas fa-comments"></i>
          </div>
        </div>
        <div class="flex-grow-1">
          <div class="d-flex align-items-center justify-content-between mb-2">
            <h6 class="mb-0 fw-bold">Message from ${booking.user_name || 'Customer'}</h6>
            <small class="text-muted">${new Date(lastMessage.timestamp).toLocaleTimeString()}</small>
          </div>
          <p class="mb-2 text-muted small">${booking.service_name}</p>
          <div class="chat-preview mb-2">
            <div class="message-bubble-preview p-2 bg-light rounded-3">
              <span class="fw-medium">${lastMessage.sender_name}:</span>
              <span class="text-muted">${lastMessage.message || lastMessage.content}</span>
            </div>
          </div>
          <div class="d-flex gap-2">
            <button class="btn btn-primary btn-sm" onclick="openBookingChat('${booking.id}')">
              <i class="fas fa-reply me-1"></i>Reply
            </button>
            <button class="btn btn-outline-secondary btn-sm" onclick="viewBookingDetails('${booking.id}')">
              <i class="fas fa-eye me-1"></i>View Details
            </button>
          </div>
        </div>
      </div>
    `;
    
    incomingEl.appendChild(chatCard);
  }

  // Open chat for a specific booking
  window.openBookingChat = function(bookingId) {
    // Create a modal for chat
    const chatModal = document.createElement('div');
    chatModal.className = 'modal fade';
    chatModal.id = 'bookingChatModal';
    chatModal.innerHTML = `
      <div class="modal-dialog modal-lg modal-dialog-centered">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">
              <i class="fas fa-comments text-primary me-2"></i>
              Chat with Customer
            </h5>
            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
          </div>
          <div class="modal-body p-0">
            <div id="bookingChatMessages" style="height: 400px; overflow-y: auto; padding: 1rem;">
              <div class="text-center text-muted py-4">
                <div class="spinner-border text-primary" role="status">
                  <span class="visually-hidden">Loading...</span>
                </div>
                <p class="mt-3">Loading messages...</p>
              </div>
            </div>
            <div class="chat-input border-top p-3 bg-white">
              <div class="input-group">
                <input type="text" class="form-control" id="bookingMessageInput" placeholder="Type your message..." onkeypress="handleBookingChatKeyPress(event, '${bookingId}')">
                <button class="btn btn-primary" type="button" onclick="sendBookingMessage('${bookingId}')">
                  <i class="fas fa-paper-plane"></i>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    `;
    
    document.body.appendChild(chatModal);
    const modal = new bootstrap.Modal(chatModal);
    modal.show();
    
    // Load chat messages
    loadBookingChatMessages(bookingId);
    
    // Remove modal when hidden
    chatModal.addEventListener('hidden.bs.modal', () => {
      chatModal.remove();
    });
  };

  // Load messages for a specific booking
  async function loadBookingChatMessages(bookingId) {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`/api/chat/${bookingId}/messages`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        displayBookingChatMessages(data.messages || []);
      }
    } catch (error) {
      console.error('Error loading booking chat messages:', error);
    }
  }

  // Display chat messages in the modal
  function displayBookingChatMessages(messages) {
    const messagesContainer = document.getElementById('bookingChatMessages');
    
    if (messages.length === 0) {
      messagesContainer.innerHTML = `
        <div class="text-center text-muted py-4">
          <i class="fas fa-comment-dots fa-2x mb-2"></i>
          <p>No messages yet. Start the conversation!</p>
        </div>
      `;
      return;
    }

    messagesContainer.innerHTML = messages.map(msg => {
      const isProvider = msg.sender_type === 'provider';
      return `
        <div class="message mb-3 ${isProvider ? 'text-end' : 'text-start'}">
          <div class="d-inline-block ${isProvider ? 'bg-primary text-white' : 'bg-light'} p-3 rounded-3" style="max-width: 70%;">
            <div class="message-text">${msg.message || msg.content}</div>
            <div class="message-time small ${isProvider ? 'text-white-50' : 'text-muted'} mt-1">
              ${new Date(msg.timestamp).toLocaleTimeString()}
            </div>
          </div>
        </div>
      `;
    }).join('');

    // Scroll to bottom
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }

  // Send message for a specific booking
  window.sendBookingMessage = async function(bookingId) {
    const messageInput = document.getElementById('bookingMessageInput');
    const message = messageInput.value.trim();
    
    if (!message) return;

    try {
      const token = localStorage.getItem('token');
      const response = await fetch('/api/chat/send', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          booking_id: bookingId,
          message: message,
          message_type: 'text'
        })
      });

      if (response.ok) {
        messageInput.value = '';
        loadBookingChatMessages(bookingId);
      } else {
        showNotification('Failed to send message', 'error');
      }
    } catch (error) {
      console.error('Error sending message:', error);
      showNotification('Error sending message', 'error');
    }
  };

  // Handle Enter key for booking chat
  window.handleBookingChatKeyPress = function(event, bookingId) {
    if (event.key === 'Enter') {
      sendBookingMessage(bookingId);
    }
  };

  // View booking details
  window.viewBookingDetails = function(bookingId) {
    window.location.href = `/track-provider?booking_id=${bookingId}`;
  };

  function showNotification(message, type = 'info') {
    // Create a modern notification
    const notification = document.createElement('div');
    notification.className = `alert alert-${type === 'success' ? 'success' : type === 'info' ? 'primary' : 'warning'} alert-dismissible fade show position-fixed`;
    notification.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
    notification.innerHTML = `
      <div class="d-flex align-items-center">
        <i class="fas fa-${type === 'success' ? 'check-circle' : type === 'info' ? 'info-circle' : 'exclamation-triangle'} me-2"></i>
        <span>${message}</span>
        <button type="button" class="btn-close ms-auto" data-bs-dismiss="alert"></button>
      </div>
    `;
    
    document.body.appendChild(notification);
    
    // Auto-remove after 5 seconds
    setTimeout(() => {
      if (notification.parentNode) {
        notification.remove();
      }
    }, 5000);
  }

  function updateBookingStatus(bookingId, newStatus) {
    // Update booking status in the table
    const rows = document.querySelectorAll('#providerJobsTable tbody tr');
    rows.forEach(row => {
      if (row.children[0].textContent === bookingId) {
        row.children[1].textContent = newStatus;
        // Add visual feedback
        row.style.backgroundColor = newStatus === 'Accepted' ? '#d1e7dd' : 
                                  newStatus === 'Rejected' ? '#f8d7da' : '';
        setTimeout(() => {
          row.style.backgroundColor = '';
        }, 2000);
      }
    });
  }

  async function renderIncoming(list){
    incoming = list;
    incomingEl.innerHTML = '';
    
    // Load chat messages from active bookings
    await loadChatMessages();
    
    if (list.length === 0 && !hasActiveChats) {
      document.getElementById('noRequests').classList.remove('d-none');
      return;
    }
    
    document.getElementById('noRequests').classList.add('d-none');
    
    // Update request count to include chat messages
    const totalCount = list.length + (hasActiveChats ? 1 : 0);
    document.getElementById('requestCount').textContent = totalCount;
    
    list.forEach(b => {
      const requestCard = document.createElement('div');
      requestCard.className = 'request-card p-3 rounded-3 border hover-lift';
      requestCard.innerHTML = `
        <div class="d-flex align-items-start justify-content-between mb-3">
          <div class="flex-grow-1">
            <h6 class="fw-bold mb-1">${b.service_name || 'Service Request'}</h6>
            <p class="text-muted small mb-2">${formatDate(b.created_at)}</p>
            <div class="d-flex align-items-center gap-3">
              <span class="badge bg-primary">₹${b.price || 0}</span>
              <span class="text-muted small">
                <i class="fas fa-map-marker-alt me-1"></i>
                ${b.location_lat ? 'Location provided' : 'Location pending'}
              </span>
            </div>
          </div>
          <div class="text-end">
            <div class="fw-bold text-primary">₹${b.price || 0}</div>
            <div class="text-muted small">${b.notes ? 'Has notes' : 'No notes'}</div>
          </div>
        </div>
        <div class="d-flex gap-2">
          <button class='btn btn-success btn-sm flex-grow-1 act' data-id='${b.id}' data-act='Accepted'>
            <i class="fas fa-check me-1"></i>Accept
          </button>
          <button class='btn btn-outline-danger btn-sm act' data-id='${b.id}' data-act='Rejected'>
            <i class="fas fa-times"></i>
          </button>
        </div>
      `;
      incomingEl.appendChild(requestCard);
    });
    
    // Update request count
    document.getElementById('requestCount').textContent = list.length;
  }

  // Load provider bookings and initialize dashboard
  (async function init(){
    try {
      // Set provider avatar
      const payload = JSON.parse(atob(token.split('.')[1]));
      const claims = payload?.sub && typeof payload.sub === 'object' ? payload.sub : (payload?.claims || payload);
      const name = claims?.name || 'Provider';
      const initials = encodeURIComponent(name.split(' ').map(p => p[0]).join('').slice(0, 2));
      document.getElementById('providerAvatar').src = `https://api.dicebear.com/7.x/avataaars/svg?seed=${initials}&backgroundColor=c7a2ff`;
      // Load current availability and set button state
      try {
        const meResp = await fetch('/me', { headers: { 'Authorization': `Bearer ${token}` }});
        if (meResp.ok) {
          const me = await meResp.json();
          const avail = me?.provider_profile?.availability;
          const btn = document.getElementById('toggleAvailability');
          if (btn && typeof avail === 'boolean') {
            if (avail) {
              btn.innerHTML = '<i class="fas fa-toggle-on me-2"></i>Available';
              btn.classList.remove('btn-secondary');
              btn.classList.add('btn-light');
            } else {
              btn.innerHTML = '<i class="fas fa-toggle-off me-2"></i>Unavailable';
              btn.classList.remove('btn-light');
              btn.classList.add('btn-secondary');
            }
          }
        }
      } catch(e) {}

    const r = await fetch('/bookings/provider', { headers: { 'Authorization': `Bearer ${token}` }});
    if (!r.ok) return;
      
    const rows = await r.json();
    const pend = rows.filter(r => r.status === 'Pending');
    renderIncoming(pend);
      updateProviderStats(rows);
      renderJobHistory(rows);
      initializeEarningsChart(rows);
      await loadMyServices();
      await loadAvailableServices();
      setupProviderEventListeners();
    } catch (error) {
      console.error('Error initializing provider dashboard:', error);
    }
  })();

  // Update provider statistics
  function updateProviderStats(bookings) {
    const totalJobs = bookings.length;
    const pendingJobs = bookings.filter(b => b.status === 'Pending').length;
    const completedJobs = bookings.filter(b => b.status === 'Completed');
    const averageRating = completedJobs.length > 0 
      ? (completedJobs.reduce((sum, b) => sum + (b.rating || 0), 0) / completedJobs.length).toFixed(1)
      : '5.0';
    const totalEarnings = bookings
      .filter(b => b.status === 'Completed')
      .reduce((sum, b) => sum + (b.price || 0), 0);

    document.getElementById('totalJobs').textContent = totalJobs;
    document.getElementById('pendingJobs').textContent = pendingJobs;
    document.getElementById('averageRating').textContent = averageRating;
    document.getElementById('totalEarnings').textContent = `₹${totalEarnings}`;
  }

  // Render job history table
  function renderJobHistory(bookings) {
    const tbody = document.querySelector('#providerJobsTable tbody');
    tbody.innerHTML = '';
    
    bookings.slice(0, 10).forEach(booking => {
      const row = document.createElement('tr');
      row.style.cursor = 'pointer';
      row.className = 'booking-row';
      
      // Make entire row clickable
      row.addEventListener('click', function(e) {
        // Don't trigger if clicking on action buttons
        if (!e.target.closest('button') && !e.target.closest('.btn-group')) {
          openBookingDetails(booking.id);
        }
      });
      
      const paymentBadge = (booking.has_payment ? `<span class="badge bg-success">Paid</span>` : `<span class="badge bg-warning text-dark">Unpaid</span>`);
      row.innerHTML = `
        <td>
          <div class="d-flex align-items-center">
            <div class="service-icon-small me-2">
              <i class="${getServiceIcon(booking.service_name)} text-primary"></i>
            </div>
            <div>
              <div class="fw-semibold">${booking.service_name || 'Service'}</div>
              <small class="text-muted">${booking.service_id || ''}</small>
            </div>
          </div>
        </td>
        <td>
          <div class="d-flex align-items-center">
            <img src="https://api.dicebear.com/7.x/avataaars/svg?seed=Customer&backgroundColor=b6e3f4" 
                 class="rounded-circle me-2" width="24" alt="Customer">
            <span>Customer</span>
          </div>
        </td>
        <td>
          <div class="d-flex align-items-center gap-2">
            <span class="badge bg-${getStatusColor(booking.status)}">${booking.status}</span>
            ${booking.status === 'Completed' ? paymentBadge : ''}
          </div>
        </td>
        <td class="fw-semibold">₹${booking.price || 0}</td>
        <td>
          <div class="small">${formatDate(booking.created_at)}</div>
        </td>
        <td>
          <div class="btn-group btn-group-sm" onclick="event.stopPropagation()">
            <button class="btn btn-outline-primary btn-sm" onclick="viewJobDetails('${booking.id}')">
              <i class="fas fa-eye"></i>
            </button>
            ${booking.status === 'Pending' ? `
              <button class="btn btn-outline-success btn-sm" onclick="acceptJob('${booking.id}')">
                <i class="fas fa-check"></i>
              </button>
            ` : ''}
            ${booking.status === 'Accepted' ? `
              <button class="btn btn-outline-info btn-sm" onclick="startJob('${booking.id}')">
                <i class="fas fa-play"></i>
              </button>
            ` : ''}
            ${booking.status === 'In Progress' ? `
              <button class="btn btn-outline-success btn-sm" onclick="completeJob('${booking.id}')">
                <i class="fas fa-check-circle"></i>
              </button>
            ` : ''}
            ${booking.status === 'Completed' && !booking.has_payment ? `
              <button class="btn btn-outline-success btn-sm" onclick="markCashPaid('${booking.id}')" title="Mark Cash Payment">
                <i class="fas fa-rupee-sign"></i>
              </button>
            ` : ''}
            ${booking.status === 'Completed' ? `
              <span class="badge bg-success">Completed</span>
            ` : ''}
          </div>
        </td>
      `;
      
      tbody.appendChild(row);
    });
  }

  // Provider marks a booking as cash paid
  window.markCashPaid = async function(bookingId){
    try{
      const token = localStorage.getItem('token');
      const r = await fetch('/payments/mark-cash', { method: 'POST', headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` }, body: JSON.stringify({ booking_id: bookingId })});
      const res = await r.json();
      if (r.ok){
        showNotification('Marked as paid (Cash).', 'success');
        await loadProviderBookings();
      } else {
        showNotification(res.message || 'Failed to mark cash payment', 'warning');
      }
    } catch(e){
      showNotification('Failed to mark cash payment', 'warning');
    }
  }
  
  // Function to open booking details page
  function openBookingDetails(bookingId) {
    window.location.href = `/provider/navigation?booking_id=${bookingId}`;
  }
  
  // Global function for opening booking details
  window.openBookingDetails = openBookingDetails;

  // Initialize earnings chart
  function initializeEarningsChart(bookings) {
    const ctx = document.getElementById('earningsChart').getContext('2d');
    
    // Generate sample data for the last 7 days
    const last7Days = [];
    const earningsData = [];
    
    for (let i = 6; i >= 0; i--) {
      const date = new Date();
      date.setDate(date.getDate() - i);
      last7Days.push(date.toLocaleDateString('en-IN', { weekday: 'short' }));
      
      // Calculate earnings for this day (sample data)
      const dayEarnings = bookings
        .filter(b => {
          const bookingDate = new Date(b.created_at);
          return bookingDate.toDateString() === date.toDateString() && b.status === 'Completed';
        })
        .reduce((sum, b) => sum + (b.price || 0), 0);
      
      earningsData.push(dayEarnings);
    }

    new Chart(ctx, {
      type: 'line',
      data: {
        labels: last7Days,
        datasets: [{
          label: 'Daily Earnings',
          data: earningsData,
          borderColor: '#0d6efd',
          backgroundColor: 'rgba(13, 110, 253, 0.1)',
          borderWidth: 3,
          fill: true,
          tension: 0.4
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            display: false
          }
        },
        scales: {
          y: {
            beginAtZero: true,
            ticks: {
              callback: function(value) {
                return '₹' + value;
              }
            }
          }
        }
      }
    });
  }

  // Setup provider event listeners
  function setupProviderEventListeners() {
    // Availability toggle
    document.getElementById('toggleAvailability')?.addEventListener('click', async function() {
      const wasAvailable = this.classList.contains('btn-light');
      const newAvailability = !wasAvailable;
      try {
        const resp = await fetch('/api/provider/availability', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
          body: JSON.stringify({ availability: newAvailability })
        });
        if (!resp.ok) throw new Error('Failed');
        // Update UI only after success
        if (newAvailability) {
          this.innerHTML = '<i class="fas fa-toggle-on me-2"></i>Available';
          this.classList.remove('btn-secondary');
          this.classList.add('btn-light');
          showNotification('You are now available', 'info');
        } else {
          this.innerHTML = '<i class="fas fa-toggle-off me-2"></i>Unavailable';
          this.classList.remove('btn-light');
          this.classList.add('btn-secondary');
          showNotification('You are now unavailable', 'info');
        }
      } catch (e) {
        showNotification('Could not update availability. Please try again.', 'warning');
      }
    });

    // Job filter buttons
    document.querySelectorAll('input[name="jobFilter"]').forEach(radio => {
      radio.addEventListener('change', function() {
        filterJobs(this.id);
      });
    });

    // Earnings period buttons
    document.querySelectorAll('input[name="earningsPeriod"]').forEach(radio => {
      radio.addEventListener('change', function() {
        updateEarningsChart(this.id);
      });
    });

    // Add service modal
    document.getElementById('saveServiceBtn').addEventListener('click', handleAddService);
  }

  // Filter jobs
  function filterJobs(filterId) {
    // This would filter the job history table
    console.log('Filter jobs:', filterId);
  }

  // Update earnings chart
  function updateEarningsChart(periodId) {
    // This would update the chart based on the selected period
    console.log('Update earnings chart:', periodId);
  }

  // Handle add service
  async function handleAddService() {
    const serviceName = document.getElementById('serviceSelect').value;
    const hourlyRate = document.getElementById('hourlyRate').value;
    const experienceLevel = document.getElementById('experienceLevel').value;
    
    if (!serviceName) {
      const msg = document.getElementById('addServiceMsg');
      msg.className = 'alert alert-danger';
      msg.querySelector('span').textContent = 'Please select a service';
      msg.classList.remove('d-none');
      return;
    }
    
    try {
      const response = await fetch('/providers/add-service', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          service_name: serviceName,
          hourly_rate: hourlyRate,
          experience_level: experienceLevel
        })
      });
      
      const result = await response.json();
      const msg = document.getElementById('addServiceMsg');
      
      if (response.ok) {
        msg.className = 'alert alert-success';
        msg.querySelector('span').textContent = 'Service added successfully!';
        msg.classList.remove('d-none');
        
        // Clear form
        document.getElementById('serviceSelect').value = '';
        document.getElementById('hourlyRate').value = '';
        document.getElementById('experienceLevel').value = 'Beginner';
        
        // Reload services
        await loadMyServices();
        
        setTimeout(() => {
          bootstrap.Modal.getInstance(document.getElementById('addServiceModal')).hide();
        }, 1500);
      } else {
        msg.className = 'alert alert-danger';
        msg.querySelector('span').textContent = result.message || 'Failed to add service';
        msg.classList.remove('d-none');
      }
    } catch (error) {
      console.error('Error adding service:', error);
      const msg = document.getElementById('addServiceMsg');
      msg.className = 'alert alert-danger';
      msg.querySelector('span').textContent = 'Failed to add service';
      msg.classList.remove('d-none');
    }
  }

  // Utility functions
  function getServiceIcon(serviceName) {
    const serviceIcons = {
      'Electrician': 'fas fa-bolt',
      'Plumber': 'fas fa-wrench',
      'Carpenter': 'fas fa-hammer',
      'Cleaner': 'fas fa-broom',
      'Painter': 'fas fa-paint-brush',
      'AC Repair': 'fas fa-snowflake'
    };
    return serviceIcons[serviceName] || 'fas fa-tools';
  }

  function getStatusColor(status) {
    switch(status) {
      case 'Pending': return 'warning';
      case 'Accepted': return 'primary';
      case 'In Progress': return 'info';
      case 'Completed': return 'success';
      case 'Cancelled': return 'danger';
      case 'Rejected': return 'danger';
      default: return 'secondary';
    }
  }

  function formatDate(dateString) {
    if (!dateString) return '';
    const date = new Date(dateString);
    return date.toLocaleDateString('en-IN', {
      day: '2-digit',
      month: 'short',
      year: 'numeric'
    });
  }

  // Load provider bookings
  async function loadProviderBookings() {
    try {
      const response = await fetch('/bookings/provider', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (response.ok) {
        const bookings = await response.json();
        updateProviderStats(bookings);
        renderJobHistory(bookings);
      }
    } catch (error) {
      console.error('Error loading provider bookings:', error);
    }
  }

  // Load my services
  async function loadMyServices() {
    try {
      const response = await fetch('/me', { 
        headers: { 'Authorization': `Bearer ${token}` } 
      });
      
      if (response.ok) {
        const userData = await response.json();
        const provider = userData.provider_profile;
        const skills = provider?.skills || [];
        
        const container = document.getElementById('myServicesList');
        container.innerHTML = '';
        
        if (skills.length === 0) {
          container.innerHTML = `
            <div class="text-center py-3">
              <i class="fas fa-tools text-muted mb-2" style="font-size: 2rem;"></i>
              <p class="text-muted small mb-0">No services added yet</p>
            </div>
          `;
        } else {
          skills.forEach(skill => {
            const serviceCard = document.createElement('div');
            serviceCard.className = 'service-item p-2 rounded-3 bg-light mb-2 d-flex align-items-center justify-content-between';
            serviceCard.innerHTML = `
              <div class="d-flex align-items-center">
                <div class="service-icon-small me-2">
                  <i class="${getServiceIcon(skill)} text-primary"></i>
                </div>
                <span class="fw-semibold">${skill}</span>
              </div>
              <button class="btn btn-outline-danger btn-sm" onclick="removeService('${skill}')">
                <i class="fas fa-times"></i>
              </button>
            `;
            container.appendChild(serviceCard);
          });
        }
        
        // Load daily rates after loading services
        await loadDailyRates(skills, provider?.daily_rates || {});
      }
    } catch (error) {
      console.error('Error loading my services:', error);
    }
  }

  // Load daily rates for services
  async function loadDailyRates(services, existingRates = {}) {
    try {
      const container = document.getElementById('dailyRatesList');
      container.innerHTML = '';
      
      if (!services || services.length === 0) {
        container.innerHTML = `
          <div class="text-center py-3">
            <i class="fas fa-calendar-day text-muted mb-2" style="font-size: 2rem;"></i>
            <p class="text-muted small mb-0">Add services first to set daily rates</p>
          </div>
        `;
        return;
      }
      
      services.forEach(service => {
        const rateCard = document.createElement('div');
        rateCard.className = 'daily-rate-item p-3 rounded-3 bg-light mb-3';
        const currentRate = existingRates[service] || '';
        rateCard.innerHTML = `
          <div class="d-flex align-items-center justify-content-between mb-2">
            <div class="d-flex align-items-center">
              <div class="service-icon-small me-2">
                <i class="${getServiceIcon(service)} text-primary"></i>
              </div>
              <span class="fw-semibold">${service}</span>
            </div>
          </div>
          <div class="input-group">
            <span class="input-group-text bg-white">₹</span>
            <input type="number" 
                   class="form-control daily-rate-input" 
                   data-service="${service}"
                   placeholder="Enter daily rate"
                   value="${currentRate}"
                   min="100"
                   step="50">
            <span class="input-group-text bg-white">/day</span>
          </div>
          <small class="text-muted">Daily rate for this service</small>
        `;
        container.appendChild(rateCard);
      });
    } catch (error) {
      console.error('Error loading daily rates:', error);
    }
  }

  // Save daily rates
  window.saveDailyRates = async function() {
    try {
      const inputs = document.querySelectorAll('.daily-rate-input');
      const dailyRates = {};
      let hasValidRates = false;
      
      inputs.forEach(input => {
        const service = input.dataset.service;
        const rate = parseFloat(input.value);
        if (rate && rate > 0) {
          dailyRates[service] = rate;
          hasValidRates = true;
        }
      });
      
      if (!hasValidRates) {
        toast('Please enter at least one daily rate');
        return;
      }
      
      const response = await fetch('/api/provider/daily-rates', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ daily_rates: dailyRates })
      });
      
      if (response.ok) {
        toast('Daily rates saved successfully!');
        const result = await response.json();
        console.log('Daily rates updated:', result.daily_rates);
      } else {
        const result = await response.json();
        toast(result.error || 'Failed to save daily rates');
      }
    } catch (error) {
      console.error('Error saving daily rates:', error);
      toast('Failed to save daily rates');
    }
  };

  // Load available services for dropdown
  async function loadAvailableServices() {
    try {
      const response = await fetch('/services');
      const services = await response.json();
      
      const select = document.getElementById('serviceSelect');
      select.innerHTML = '<option value="">Choose a service...</option>';
      
      services.forEach(service => {
        const option = document.createElement('option');
        option.value = service.name;
        option.textContent = `${service.name} (${service.category})`;
        select.appendChild(option);
      });
    } catch (error) {
      console.error('Error loading available services:', error);
    }
  }

  // Global functions for buttons
  window.refreshRequests = function() {
    // Reload incoming requests
    location.reload();
  };

  window.viewAnalytics = function() {
    // Implement analytics view
    console.log('View analytics');
  };

  window.viewJobDetails = function(jobId) {
    // Implement job details modal
    console.log('View job details:', jobId);
  };

  window.acceptJob = async function(jobId) {
    try {
      const response = await fetch(`/bookings/${jobId}/status`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ status: 'Accepted' })
      });
      
      if (response.ok) {
        showNotification('Job accepted successfully!', 'success');
        loadProviderBookings();
      } else {
        showNotification('Failed to accept job', 'error');
      }
    } catch (error) {
      console.error('Error accepting job:', error);
      showNotification('Failed to accept job', 'error');
    }
  };

  window.startJob = async function(jobId) {
    try {
      const response = await fetch(`/bookings/${jobId}/status`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ status: 'In Progress' })
      });
      
      if (response.ok) {
        showNotification('Job started!', 'success');
        loadProviderBookings();
      } else {
        showNotification('Failed to start job', 'error');
      }
    } catch (error) {
      console.error('Error starting job:', error);
      showNotification('Failed to start job', 'error');
    }
  };

  window.completeJob = function(jobId) {
    // Create service completion modal
    const modal = document.createElement('div');
    modal.className = 'modal fade';
    modal.innerHTML = `
      <div class="modal-dialog modal-lg">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">Complete Service</h5>
            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
          </div>
          <div class="modal-body">
            <form id="completionForm" enctype="multipart/form-data">
              <div class="mb-3">
                <label class="form-label fw-semibold">Completion Notes <span class="text-danger">*</span></label>
                <textarea class="form-control" id="completionNotes" rows="4" 
                          placeholder="Describe what work was completed..." required></textarea>
                <div class="invalid-feedback">Completion notes are required</div>
              </div>
              <div class="mb-3">
                <label class="form-label fw-semibold">Upload Completion Images <span class="text-danger">*</span></label>
                <input type="file" class="form-control" id="completionImages" 
                       multiple accept="image/*" required />
                <div class="form-text">Upload photos showing the completed work</div>
                <div class="invalid-feedback">At least one completion image is required</div>
              </div>
              <div id="completionMsg" class="alert alert-info d-none">
                <i class="fas fa-info-circle me-2"></i>
                <span></span>
              </div>
            </form>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
            <button type="button" class="btn btn-success" id="submitCompletion">
              <i class="fas fa-check-circle me-2"></i>Complete Service
            </button>
          </div>
        </div>
      </div>
    `;
    
    document.body.appendChild(modal);
    const bsModal = new bootstrap.Modal(modal);
    bsModal.show();
    
    // Handle form submission
    modal.querySelector('#submitCompletion').addEventListener('click', async function() {
      const completionNotes = modal.querySelector('#completionNotes').value.trim();
      const images = modal.querySelector('#completionImages').files;
      const notesTextarea = modal.querySelector('#completionNotes');
      const imagesInput = modal.querySelector('#completionImages');
      const form = modal.querySelector('#completionForm');
      
      // Reset validation
      notesTextarea.classList.remove('is-invalid');
      imagesInput.classList.remove('is-invalid');
      
      // Validate fields
      let isValid = true;
      
      if (!completionNotes || completionNotes.length === 0) {
        notesTextarea.classList.add('is-invalid');
        isValid = false;
      }
      
      if (!images || images.length === 0) {
        imagesInput.classList.add('is-invalid');
        isValid = false;
      }
      
      if (!isValid) {
        const msg = modal.querySelector('#completionMsg');
        msg.className = 'alert alert-danger';
        msg.querySelector('span').textContent = 'Please fill in all required fields (Completion Notes and at least one image)';
        msg.classList.remove('d-none');
        return;
      }
      
      try {
        const formData = new FormData();
        formData.append('booking_id', jobId);
        formData.append('completion_notes', completionNotes);
        
        // Add images to form data
        for (let i = 0; i < images.length; i++) {
          formData.append('images', images[i]);
        }
        
        const response = await fetch('/completion/upload', {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`
          },
          body: formData
        });
        
        const result = await response.json();
        const msg = modal.querySelector('#completionMsg');
        
        if (response.ok) {
          msg.className = 'alert alert-success';
          msg.querySelector('span').textContent = 'Service completed successfully!';
          msg.classList.remove('d-none');
          
          showNotification('Service completed and uploaded!', 'success');
          
          setTimeout(() => {
            bsModal.hide();
            loadProviderBookings();
          }, 1500);
        } else {
          msg.className = 'alert alert-danger';
          msg.querySelector('span').textContent = result.message || 'Failed to complete service';
          msg.classList.remove('d-none');
        }
      } catch (error) {
        console.error('Error completing service:', error);
        const msg = modal.querySelector('#completionMsg');
        msg.className = 'alert alert-danger';
        msg.querySelector('span').textContent = 'Failed to complete service';
        msg.classList.remove('d-none');
      }
    });
    
    // Remove modal after hiding
    modal.addEventListener('hidden.bs.modal', () => modal.remove());
  };

  window.removeService = async function(serviceName) {
    if (!confirm(`Are you sure you want to remove "${serviceName}" from your services?`)) {
      return;
    }
    
    try {
      const response = await fetch('/providers/remove-service', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ service_name: serviceName })
      });
      
      if (response.ok) {
        showNotification('Service removed successfully!', 'success');
        await loadMyServices();
      } else {
        showNotification('Failed to remove service', 'error');
      }
    } catch (error) {
      console.error('Error removing service:', error);
      showNotification('Failed to remove service', 'error');
    }
  };

  incomingEl.addEventListener('click', async (e) => {
    const btn = e.target.closest('.act');
    if (!btn) return;
    const id = btn.getAttribute('data-id');
    const act = btn.getAttribute('data-act');
    const r = await fetch(`/bookings/${act === 'Accepted' ? 'accept' : 'reject'}`, { method: 'POST', headers: { 'Content-Type':'application/json', 'Authorization': `Bearer ${token}` }, body: JSON.stringify({ booking_id: id })});
    if (r.ok){
      renderIncoming(incoming.filter(b => b.id !== id));
    }
  });
})();






