// Enhanced Profile Page JavaScript - Amazon/Zepto Style
(function() {
  'use strict';
  
  const token = localStorage.getItem('token') || '';
  let userData = {};
  let bookings = [];
  let addresses = [];
  let transactions = [];
  
  // Initialize profile page
  document.addEventListener('DOMContentLoaded', async function() {
    if (!token) {
      window.location.href = '/login';
      return;
    }
    
    // Setup sidebar navigation
    setupSidebarNavigation();
    
    // Load user data
    await loadUserData();
    
    // Load all sections data
    await loadDashboardData();
    
    // Setup form handlers
    setupFormHandlers();
    
    // Setup avatar upload
    setupAvatarUpload();
  });

  // Setup sidebar navigation
  function setupSidebarNavigation() {
    document.querySelectorAll('.profile-sidebar .nav-link[data-section]').forEach(link => {
      link.addEventListener('click', function(e) {
        e.preventDefault();
        const section = this.getAttribute('data-section');
        showSection(section);
      });
    });
  }

  // Show specific section
  window.showSection = function(section) {
    // Hide all sections
    document.querySelectorAll('.profile-section').forEach(sec => {
      sec.style.display = 'none';
    });
    
    // Show selected section
    const selectedSection = document.getElementById(`section-${section}`);
    if (selectedSection) {
      selectedSection.style.display = 'block';
      
      // Load section data if needed
      if (section === 'orders') {
        loadOrders();
      } else if (section === 'addresses') {
        loadAddresses();
      } else if (section === 'wallet') {
        loadWalletData();
      } else if (section === 'referrals') {
        loadReferralData();
      } else if (section === 'settings') {
        loadSettings();
      } else if (section === 'notifications') {
        loadNotifications();
      }
    }
    
    // Update active nav link
    document.querySelectorAll('.profile-sidebar .nav-link').forEach(link => {
      link.classList.remove('active');
      if (link.getAttribute('data-section') === section) {
        link.classList.add('active');
      }
    });
  };

  // Load user data
  async function loadUserData() {
    try {
      const response = await fetch('/api/user/profile', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (!response.ok) {
        if (response.status === 401) {
          window.location.href = '/login';
          return;
        }
        throw new Error('Failed to load profile');
      }
      
      userData = await response.json();
      
      // Update header
      document.getElementById('profName').textContent = userData.name || 'Your Name';
      document.getElementById('profEmail').textContent = userData.email || 'you@example.com';
      const ratingEl = document.getElementById('userRating');
      if (ratingEl) {
        ratingEl.innerHTML = `<i class="fas fa-star text-warning"></i> ${(userData.rating || 0).toFixed(1)}`;
      }
      document.getElementById('walletCredits').textContent = `₹${(userData.credits || 0).toFixed(2)}`;
      document.getElementById('walletBalance').textContent = `₹${(userData.credits || 0).toFixed(2)}`;
      
      // Update avatar
      if (userData.avatar_url) {
        document.getElementById('profAvatar').src = userData.avatar_url;
      } else {
        const name = userData.name || 'User';
        const initials = encodeURIComponent(name.split(' ').map(p => p[0]).join('').slice(0, 2));
        document.getElementById('profAvatar').src = `https://api.dicebear.com/7.x/avataaars/svg?seed=${initials}&backgroundColor=b6e3f4`;
      }
      
      // Update member since
      if (userData.created_at) {
        const date = new Date(userData.created_at);
        document.getElementById('memberSince').textContent = date.getFullYear();
      }
      
      // Prefill edit form
      document.getElementById('editName').value = userData.name || '';
      document.getElementById('editEmail').value = userData.email || '';
      document.getElementById('editPhone').value = userData.phone || '';
      
    } catch (error) {
      console.error('Error loading user data:', error);
      showNotification('Failed to load profile data', 'error');
    }
  }

  // Load dashboard data
  async function loadDashboardData() {
    try {
      // Load bookings
      const bookingsResponse = await fetch('/bookings/user', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (bookingsResponse.ok) {
        bookings = await bookingsResponse.json();
        
        // Update statistics
        updateStatistics(bookings);
        
        // Update orders badge
        document.getElementById('ordersBadge').textContent = bookings.length;
        
        // Load recent orders
        loadRecentOrders(bookings.slice(0, 5));
      }
      
    } catch (error) {
      console.error('Error loading dashboard data:', error);
    }
  }

  // Update statistics
  function updateStatistics(bookingsList) {
    const totalBookings = bookingsList.length;
    const completedBookings = bookingsList.filter(b => b.status === 'Completed').length;
    const activeBookings = bookingsList.filter(b => ['Pending', 'Accepted', 'In Progress'].includes(b.status)).length;
    const totalSpent = bookingsList
      .filter(b => b.status === 'Completed' && b.has_payment)
      .reduce((sum, b) => sum + (b.price || 0), 0);
    
    document.getElementById('totalBookings').textContent = totalBookings;
    document.getElementById('completedBookings').textContent = completedBookings;
    document.getElementById('activeBookings').textContent = activeBookings;
    document.getElementById('totalSpent').textContent = `₹${totalSpent}`;
  }

  // Load recent orders
  function loadRecentOrders(recentBookings) {
    const container = document.getElementById('recentOrdersList');
    
    if (!recentBookings || recentBookings.length === 0) {
      container.innerHTML = `
        <div class="empty-state">
          <i class="fas fa-shopping-bag"></i>
          <h6>No orders yet</h6>
          <p class="small">Start booking services to see your orders here</p>
          <a href="/booking-map" class="btn btn-primary btn-sm mt-2">
            <i class="fas fa-plus me-1"></i>Book Service
          </a>
        </div>
      `;
      return;
    }
    
      container.innerHTML = recentBookings.map(booking => `
      <div class="booking-item">
        <div class="row align-items-center">
          <div class="col-md-6">
            <div class="d-flex align-items-center">
              <div class="service-icon me-3">
                <i class="fas fa-tools fa-2x text-primary"></i>
              </div>
              <div>
                <h6 class="mb-1 fw-semibold">${booking.service_name || 'Service'}</h6>
                <p class="small text-muted mb-0">Order #${booking.id.slice(-8)}</p>
                <p class="small text-muted mb-0">${formatDate(booking.created_at)}</p>
              </div>
            </div>
          </div>
          <div class="col-md-3 text-center">
            <span class="badge bg-${getStatusColor(booking.status)}">${booking.status}</span>
            <p class="small text-muted mb-0 mt-1">₹${booking.price || 0}</p>
          </div>
          <div class="col-md-3 text-end">
            <button class="btn btn-sm btn-outline-primary" onclick="viewBookingDetails('${booking.id}')">
              View Details
            </button>
          </div>
        </div>
      </div>
    `).join('');
  }

  // Load orders
  async function loadOrders() {
    try {
      const container = document.getElementById('ordersList');
      container.innerHTML = '<div class="text-center py-4"><div class="spinner-border" role="status"></div></div>';
      
      if (!bookings || bookings.length === 0) {
        container.innerHTML = `
          <div class="empty-state">
            <i class="fas fa-shopping-bag"></i>
            <h6>No orders yet</h6>
            <p class="small">Start booking services to see your orders here</p>
            <a href="/booking-map" class="btn btn-primary btn-sm mt-2">
              <i class="fas fa-plus me-1"></i>Book Service
            </a>
          </div>
        `;
        return;
      }
      
      let filteredBookings = bookings;
      const filter = document.querySelector('input[name="orderFilter"]:checked');
      if (filter && filter.id === 'pendingOrders') {
        filteredBookings = bookings.filter(b => !['Completed', 'Cancelled'].includes(b.status));
      } else if (filter && filter.id === 'completedOrders') {
        filteredBookings = bookings.filter(b => b.status === 'Completed');
      }
      
      container.innerHTML = filteredBookings.map(booking => `
        <div class="booking-item">
          <div class="row align-items-center">
            <div class="col-md-4">
              <div class="d-flex align-items-center">
                <div class="service-icon me-3">
                  <i class="fas fa-tools fa-2x text-primary"></i>
                </div>
                <div>
                  <h6 class="mb-1 fw-semibold">${booking.service_name || 'Service'}</h6>
                  <p class="small text-muted mb-0">Order #${booking.id.slice(-8)}</p>
                  <p class="small text-muted mb-0">${formatDate(booking.created_at)}</p>
                </div>
              </div>
            </div>
            <div class="col-md-2 text-center">
              <span class="badge bg-${getStatusColor(booking.status)}">${booking.status}</span>
            </div>
            <div class="col-md-2 text-center">
              <p class="fw-semibold mb-0">₹${booking.price || 0}</p>
            </div>
            <div class="col-md-2 text-center">
              ${booking.rating ? `
                <div class="text-warning">${'⭐'.repeat(booking.rating)}</div>
              ` : booking.status === 'Completed' ? `
                <button class="btn btn-sm btn-outline-warning" onclick="rateBooking('${booking.id}')">
                  Rate
                </button>
              ` : '<span class="text-muted small">-</span>'}
            </div>
            <div class="col-md-2 text-end">
              <button class="btn btn-sm btn-outline-primary" onclick="viewBookingDetails('${booking.id}')">
                View
              </button>
            </div>
          </div>
        </div>
      `).join('');
      
      // Setup filter listeners
      document.querySelectorAll('input[name="orderFilter"]').forEach(radio => {
        radio.addEventListener('change', loadOrders);
      });
      
    } catch (error) {
      console.error('Error loading orders:', error);
      showNotification('Failed to load orders', 'error');
    }
  }

  // Load addresses
  async function loadAddresses() {
    try {
      const response = await fetch('/profile/addresses', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      const container = document.getElementById('addressesList');
      
      if (!response.ok) {
        container.innerHTML = '<div class="empty-state"><i class="fas fa-map-marker-alt"></i><h6>No addresses</h6></div>';
        return;
      }
      
      addresses = await response.json();
      
      if (!addresses || addresses.length === 0) {
        container.innerHTML = `
          <div class="empty-state">
            <i class="fas fa-map-marker-alt"></i>
            <h6>No saved addresses</h6>
            <p class="small">Add an address for faster checkout</p>
            <button class="btn btn-primary btn-sm mt-2" data-bs-toggle="modal" data-bs-target="#addAddressModal">
              <i class="fas fa-plus me-1"></i>Add Address
            </button>
          </div>
        `;
        return;
      }
      
      container.innerHTML = addresses.map(addr => `
        <div class="address-card ${addr.is_default ? 'default' : ''}">
          ${addr.is_default ? '<span class="badge-default">Default</span>' : ''}
          <h6 class="fw-semibold mb-2">${addr.label || 'Address'}</h6>
          <p class="text-muted mb-3">${addr.address}</p>
          <div class="d-flex gap-2">
            ${!addr.is_default ? `
              <button class="btn btn-sm btn-outline-primary" onclick="setDefaultAddress('${addr.uid}')">
                Set as Default
              </button>
            ` : ''}
            <button class="btn btn-sm btn-outline-danger" onclick="deleteAddress('${addr.uid}')">
              <i class="fas fa-trash me-1"></i>Delete
            </button>
          </div>
        </div>
      `).join('');
      
    } catch (error) {
      console.error('Error loading addresses:', error);
      showNotification('Failed to load addresses', 'error');
    }
  }

  // Load wallet data
  async function loadWalletData() {
    try {
      // Update wallet balance
      document.getElementById('walletBalance').textContent = `₹${(userData.credits || 0).toFixed(2)}`;
      
      // Load transactions
      const response = await fetch('/api/wallet', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      const container = document.getElementById('transactionsList');
      
      if (!response.ok) {
        container.innerHTML = '<div class="empty-state"><i class="fas fa-wallet"></i><h6>No transactions</h6></div>';
        return;
      }
      
      const walletData = await response.json();
      transactions = walletData.transactions || [];
      
      if (!transactions || transactions.length === 0) {
        container.innerHTML = `
          <div class="empty-state">
            <i class="fas fa-wallet"></i>
            <h6>No transactions yet</h6>
            <p class="small">Your wallet transactions will appear here</p>
          </div>
        `;
        return;
      }
      
      container.innerHTML = transactions.map(tx => `
        <div class="transaction-item ${tx.transaction_type}">
          <div>
            <h6 class="mb-1 fw-semibold">${tx.description || tx.source}</h6>
            <p class="small text-muted mb-0">${formatDate(tx.created_at)}</p>
          </div>
          <div class="text-end">
            <div class="amount fw-bold">
              ${tx.transaction_type === 'credit' ? '+' : '-'}₹${tx.amount.toFixed(2)}
            </div>
            <p class="small text-muted mb-0">Balance: ₹${tx.balance_after.toFixed(2)}</p>
          </div>
        </div>
      `).join('');
      
    } catch (error) {
      console.error('Error loading wallet data:', error);
      showNotification('Failed to load wallet data', 'error');
    }
  }

  // Load referral data
  async function loadReferralData() {
    try {
      const response = await fetch('/api/wallet', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (response.ok) {
        const walletData = await response.json();
        const referralCode = walletData.referral_code || 'N/A';
        document.getElementById('referralCodeInput').value = referralCode;
        document.getElementById('referralCount').textContent = '0'; // Update with actual count if available
      }
    } catch (error) {
      console.error('Error loading referral data:', error);
    }
  }

  // Load settings
  function loadSettings() {
    // Settings are already pre-filled in loadUserData()
  }

  // Load notifications
  async function loadNotifications() {
    try {
      const response = await fetch('/profile/preferences', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (response.ok) {
        const prefs = await response.json();
        document.getElementById('prefEmail').checked = prefs.prefers_email_notifications || false;
        document.getElementById('prefSms').checked = prefs.prefers_sms_notifications || false;
        document.getElementById('prefDark').checked = prefs.dark_mode || false;
        document.getElementById('prefLang').value = prefs.language || 'en';
      }
    } catch (error) {
      console.error('Error loading notifications:', error);
    }
  }

  // Setup form handlers
  function setupFormHandlers() {
    // Profile save
    document.getElementById('saveProfileBtn')?.addEventListener('click', handleProfileSave);
    
    // Password change
    document.getElementById('savePassBtn')?.addEventListener('click', handlePasswordChange);
    
    // Preferences save
    document.getElementById('savePrefBtn')?.addEventListener('click', savePreferences);
    
    // Address save
    document.getElementById('saveAddrBtn')?.addEventListener('click', handleAddressSave);
  }

  // Setup avatar upload
  function setupAvatarUpload() {
    document.getElementById('avatarInput')?.addEventListener('change', async function(e) {
      const file = e.target.files[0];
      if (!file) return;
      
      try {
        const formData = new FormData();
        formData.append('avatar', file);
        
        const response = await fetch('/profile/avatar', {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${token}` },
          body: formData
        });
        
        const result = await response.json();
        if (response.ok && result.avatar_url) {
          document.getElementById('profAvatar').src = result.avatar_url;
          showNotification('Avatar updated successfully!', 'success');
        } else {
          showNotification(result.message || 'Failed to update avatar', 'error');
        }
      } catch (error) {
        console.error('Error uploading avatar:', error);
        showNotification('Failed to update avatar', 'error');
      }
    });
  }

  // Handle profile save
  async function handleProfileSave() {
    const payload = {
      name: document.getElementById('editName').value,
      email: document.getElementById('editEmail').value,
      phone: document.getElementById('editPhone').value
    };
    
    try {
      const response = await fetch('/profile/update', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(payload)
      });
      
      const result = await response.json();
      
      if (response.ok) {
        showNotification('Profile updated successfully!', 'success');
        await loadUserData();
      } else {
        showNotification(result.message || 'Failed to update profile', 'error');
      }
    } catch (error) {
      console.error('Error updating profile:', error);
      showNotification('Failed to update profile', 'error');
    }
  }

  // Handle password change
  async function handlePasswordChange() {
    const currentPassword = document.getElementById('curPass').value;
    const newPassword = document.getElementById('newPass').value;
    const confirmPassword = document.getElementById('confirmPass').value;
    
    if (newPassword !== confirmPassword) {
      showNotification('New passwords do not match', 'error');
      return;
    }
    
    if (newPassword.length < 8) {
      showNotification('Password must be at least 8 characters long', 'error');
      return;
    }
    
    try {
      const response = await fetch('/profile/password', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword
        })
      });
      
      const result = await response.json();
      
      if (response.ok) {
        showNotification('Password changed successfully!', 'success');
        document.getElementById('curPass').value = '';
        document.getElementById('newPass').value = '';
        document.getElementById('confirmPass').value = '';
      } else {
        showNotification(result.message || 'Failed to change password', 'error');
      }
    } catch (error) {
      console.error('Error changing password:', error);
      showNotification('Failed to change password', 'error');
    }
  }

  // Save preferences
  async function savePreferences() {
    const payload = {
      prefers_email_notifications: document.getElementById('prefEmail').checked,
      prefers_sms_notifications: document.getElementById('prefSms').checked,
      dark_mode: document.getElementById('prefDark').checked,
      language: document.getElementById('prefLang').value
    };
    
    try {
      const response = await fetch('/profile/preferences', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(payload)
      });
      
      if (response.ok) {
        showNotification('Preferences saved successfully!', 'success');
      } else {
        showNotification('Failed to save preferences', 'error');
      }
    } catch (error) {
      console.error('Error saving preferences:', error);
      showNotification('Failed to save preferences', 'error');
    }
  }

  // Handle address save
  async function handleAddressSave() {
    const payload = {
      label: document.getElementById('addrLabel').value,
      address: document.getElementById('addrText').value,
      latitude: parseFloat(document.getElementById('addrLat').value),
      longitude: parseFloat(document.getElementById('addrLon').value),
      is_default: document.getElementById('addrDefault').checked
    };
    
    try {
      const response = await fetch('/profile/addresses', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(payload)
      });
      
      if (response.ok) {
        showNotification('Address saved successfully!', 'success');
        bootstrap.Modal.getInstance(document.getElementById('addAddressModal')).hide();
        document.getElementById('addressForm').reset();
        await loadAddresses();
      } else {
        showNotification('Failed to save address', 'error');
      }
    } catch (error) {
      console.error('Error saving address:', error);
      showNotification('Failed to save address', 'error');
    }
  }

  // Set default address
  window.setDefaultAddress = async function(uid) {
    try {
      const response = await fetch(`/profile/addresses/${uid}/default`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (response.ok) {
        showNotification('Default address updated!', 'success');
        await loadAddresses();
      }
    } catch (error) {
      console.error('Error setting default address:', error);
      showNotification('Failed to update default address', 'error');
    }
  };

  // Delete address
  window.deleteAddress = async function(uid) {
    if (!confirm('Are you sure you want to delete this address?')) return;
    
    try {
      const response = await fetch(`/profile/addresses/${uid}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (response.ok) {
        showNotification('Address deleted!', 'success');
        await loadAddresses();
      }
    } catch (error) {
      console.error('Error deleting address:', error);
      showNotification('Failed to delete address', 'error');
    }
  };

  // Copy referral code
  window.copyReferralCode = function() {
    const input = document.getElementById('referralCodeInput');
    input.select();
    document.execCommand('copy');
    showNotification('Referral code copied!', 'success');
  };

  // View booking details
  window.viewBookingDetails = function(bookingId) {
    window.location.href = `/dashboard?booking=${bookingId}`;
  };

  // Rate booking
  window.rateBooking = function(bookingId) {
    window.location.href = `/dashboard?rate=${bookingId}`;
  };

  // Utility functions
  function getStatusColor(status) {
    switch(status) {
      case 'Pending': return 'warning';
      case 'Accepted': return 'primary';
      case 'In Progress': return 'info';
      case 'Completed': return 'success';
      case 'Cancelled': return 'secondary';
      case 'Rejected': return 'danger';
      default: return 'light';
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

  function showNotification(message, type) {
    const notification = document.createElement('div');
    notification.className = `alert alert-${type === 'success' ? 'success' : 'danger'} alert-dismissible fade show position-fixed`;
    notification.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
    notification.innerHTML = `
      <div class="d-flex align-items-center">
        <i class="fas fa-${type === 'success' ? 'check-circle' : 'exclamation-triangle'} me-2"></i>
        <span>${message}</span>
        <button type="button" class="btn-close ms-auto" data-bs-dismiss="alert"></button>
      </div>
    `;
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
      if (notification.parentNode) {
        notification.remove();
      }
    }, 5000);
  }

})();

