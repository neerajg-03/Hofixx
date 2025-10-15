// Enhanced User Dashboard JavaScript
(function() {
  'use strict';
  
  // Global variables
  let map;
  let userLat = null, userLon = null;
  let userBookings = [];
  let providers = [];
  let socket;
  let currentUserId = null;
  
  // Service icons mapping
  const serviceIcons = {
    'Electrician': 'fas fa-bolt',
    'Plumber': 'fas fa-wrench',
    'Carpenter': 'fas fa-hammer',
    'Cleaner': 'fas fa-broom',
    'Painter': 'fas fa-paint-brush',
    'AC Repair': 'fas fa-snowflake'
  };

  // Initialize dashboard
  document.addEventListener('DOMContentLoaded', async function() {
    try {
      console.log('Initializing dashboard...');
      await initializeDashboard();
      console.log('Dashboard initialized');
      
      await initializeSocket();
      console.log('Socket initialized');
      
      await loadUserData();
      console.log('User data loaded');
      
      await loadPopularServices();
      console.log('Popular services loaded');
      
      await loadUserBookings();
      console.log('User bookings loaded');
      
      await initializeMap();
      console.log('Map initialized');
      
      setupEventListeners();
      console.log('Event listeners setup');
      
      console.log('Dashboard initialization complete!');
    } catch (error) {
      console.error('Error during dashboard initialization:', error);
      
      // Show error message to user
      const errorDiv = document.createElement('div');
      errorDiv.className = 'alert alert-danger m-3';
      errorDiv.innerHTML = `
        <h5>Dashboard Loading Error</h5>
        <p>There was an error loading the dashboard. Please try refreshing the page.</p>
        <button class="btn btn-outline-danger btn-sm" onclick="location.reload()">Refresh Page</button>
      `;
      document.body.insertBefore(errorDiv, document.body.firstChild);
    }
  });

  // Initialize dashboard components
  async function initializeDashboard() {
    // Set user avatar based on token
    const token = localStorage.getItem('token');
    if (token) {
      try {
        const payload = JSON.parse(atob(token.split('.')[1]));
        const claims = payload?.sub && typeof payload.sub === 'object' ? payload.sub : (payload?.claims || payload);
        const name = claims?.name || 'User';
        currentUserId = claims?.id || claims?.user_id;
        const initials = encodeURIComponent(name.split(' ').map(p => p[0]).join('').slice(0, 2));
        document.getElementById('userAvatar').src = `https://api.dicebear.com/7.x/avataaars/svg?seed=${initials}&backgroundColor=b6e3f4`;
      } catch (e) {
        console.error('Error parsing token:', e);
      }
    }
  }

  // Initialize Socket.IO for real-time updates
  async function initializeSocket() {
    try {
      socket = io();
      
      socket.on('connect', () => {
        console.log('Connected to server');
        if (currentUserId) {
          socket.emit('join', { room: `user_${currentUserId}` });
          console.log(`User ${currentUserId} joined socket room`);
        }
      });

      socket.on('disconnect', () => {
        console.log('Disconnected from server');
      });

      // Listen for booking updates
      socket.on('booking_updated', (data) => {
        console.log('Booking updated:', data);
        showNotification('Booking status updated!', 'info');
        loadUserBookings(); // Refresh bookings
        loadUserData(); // Refresh stats
      });

      // Listen for provider location updates
      socket.on('provider_location', (data) => {
        console.log('Provider location update:', data);
        updateProviderLocation(data);
      });

      // Listen for booking status changes
      socket.on('booking_status_change', (data) => {
        console.log('Booking status changed:', data);
        showNotification(`Booking status: ${data.status}`, 'info');
        loadUserBookings();
      });

    } catch (error) {
      console.error('Error initializing socket:', error);
    }
  }

  // Load user data and statistics
  async function loadUserData() {
    const token = localStorage.getItem('token');
    if (!token) {
      console.log('No token found, skipping user data load');
      return;
    }

    try {
      console.log('Loading user data...');
      const response = await fetch('/me', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      console.log('User data response status:', response.status);
      
      if (response.ok) {
        const userData = await response.json();
        console.log('User data loaded:', userData);
        
        // Update user info in the UI
        if (userData.name) {
          const nameElement = document.querySelector('.user-name');
          if (nameElement) nameElement.textContent = userData.name;
        }
        
        if (userData.email) {
          const emailElement = document.querySelector('.user-email');
          if (emailElement) emailElement.textContent = userData.email;
        }
        
        // Update stats if we have bookings data
        if (userBookings && userBookings.length > 0) {
          updateUserStats(userBookings);
        }
      } else {
        const error = await response.text();
        console.error('Error loading user data:', response.status, error);
      }
    } catch (error) {
      console.error('Error loading user data:', error);
    }
  }

  // Update user statistics
  function updateUserStats(bookings) {
    const totalBookings = bookings.length;
    const activeBookings = bookings.filter(b => ['Pending', 'Accepted', 'In Progress'].includes(b.status)).length;
    const completedBookings = bookings.filter(b => b.status === 'Completed');
    const averageRating = completedBookings.length > 0 
      ? (completedBookings.reduce((sum, b) => sum + (b.rating || 0), 0) / completedBookings.length).toFixed(1)
      : '5.0';
    const totalSpent = bookings
      .filter(b => b.status === 'Completed')
      .reduce((sum, b) => sum + (b.price || 0), 0);

    document.getElementById('totalBookings').textContent = totalBookings;
    document.getElementById('activeBookings').textContent = activeBookings;
    document.getElementById('averageRating').textContent = averageRating;
    document.getElementById('totalSpent').textContent = `₹${totalSpent}`;
  }

  // Load popular services
  async function loadPopularServices() {
    try {
      const response = await fetch('/services');
      const services = await response.json();
      const container = document.getElementById('popularServices');
      
      container.innerHTML = '';
      
      services.slice(0, 4).forEach((service, index) => {
        const icon = serviceIcons[service.name] || 'fas fa-tools';
        const serviceCard = document.createElement('div');
        serviceCard.className = 'col-6 col-md-3';
        serviceCard.innerHTML = `
          <div class="service-mini-card p-3 rounded-3 bg-white border hover-lift text-center">
            <div class="service-icon-small mb-2">
              <i class="${icon} text-primary"></i>
            </div>
            <h6 class="mb-1 fw-bold">${service.name}</h6>
            <p class="text-muted small mb-2">${service.category}</p>
            <div class="fw-bold text-primary mb-2">From ₹${service.base_price}</div>
            <a href="/booking-map?service_id=${service.id}" class="btn btn-outline-primary btn-sm rounded-pill w-100">
              Book Now
            </a>
          </div>
        `;
        container.appendChild(serviceCard);
      });
    } catch (error) {
      console.error('Error loading services:', error);
    }
  }

  // Load user bookings
  async function loadUserBookings() {
    const token = localStorage.getItem('token');
    if (!token) {
      console.log('No token found, skipping bookings load');
      return;
    }

    try {
      console.log('Loading user bookings...');
      const response = await fetch('/bookings/user', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      console.log('Bookings response status:', response.status);
      
      if (response.ok) {
        const bookings = await response.json();
        console.log('Bookings loaded:', bookings);
        renderUserBookings(bookings);
      } else {
        const error = await response.text();
        console.error('Error loading bookings:', response.status, error);
        
        // Show error in the table
        const tbody = document.querySelector('#userBookingsTable tbody');
        if (tbody) {
          const loadingRow = document.getElementById('loadingRow');
          if (loadingRow) loadingRow.remove();
          
          tbody.innerHTML = `
            <tr>
              <td colspan="6" class="text-center py-4 text-danger">
                <i class="fas fa-exclamation-triangle fa-2x mb-3"></i>
                <div>Error loading bookings</div>
                <small>Status: ${response.status} - ${error}</small>
                <div class="mt-2">
                  <button class="btn btn-outline-primary btn-sm" onclick="loadUserBookings()">
                    <i class="fas fa-refresh"></i> Retry
                  </button>
                </div>
              </td>
            </tr>
          `;
        }
      }
    } catch (error) {
      console.error('Error loading bookings:', error);
      
      // Show error in the table
      const tbody = document.querySelector('#userBookingsTable tbody');
      if (tbody) {
        const loadingRow = document.getElementById('loadingRow');
        if (loadingRow) loadingRow.remove();
        
        tbody.innerHTML = `
          <tr>
            <td colspan="6" class="text-center py-4 text-danger">
              <i class="fas fa-exclamation-triangle fa-2x mb-3"></i>
              <div>Error loading bookings</div>
              <small>${error.message}</small>
              <div class="mt-2">
                <button class="btn btn-outline-primary btn-sm" onclick="loadUserBookings()">
                  <i class="fas fa-refresh"></i> Retry
                </button>
              </div>
            </td>
          </tr>
        `;
      }
    }
  }

  // Render user bookings table
  function renderUserBookings(bookings) {
    console.log('Rendering user bookings:', bookings);
    const tbody = document.querySelector('#userBookingsTable tbody');
    
    if (!tbody) {
      console.error('Table body not found!');
      return;
    }
    
    tbody.innerHTML = '';
    
    // Remove loading row
    const loadingRow = document.getElementById('loadingRow');
    if (loadingRow) {
      loadingRow.remove();
    }
    
    if (!bookings || bookings.length === 0) {
      console.log('No bookings to render');
      tbody.innerHTML = `
        <tr>
          <td colspan="6" class="text-center py-4 text-muted">
            <i class="fas fa-calendar-times fa-2x mb-3"></i>
            <div>No bookings found</div>
            <small>Your service requests will appear here</small>
            <div class="mt-2">
              <button class="btn btn-primary btn-sm" onclick="window.location.href='/services'">
                <i class="fas fa-plus"></i> Book a Service
              </button>
            </div>
          </td>
        </tr>
      `;
      return;
    }
    
    console.log(`Rendering ${bookings.length} bookings`);
    bookings.slice(0, 10).forEach(booking => {
      const row = document.createElement('tr');
      row.innerHTML = `
        <td>
          <div class="d-flex align-items-center">
            <div class="service-icon-small me-2">
              <i class="${serviceIcons[booking.service_name] || 'fas fa-tools'} text-primary"></i>
            </div>
            <div>
              <div class="fw-semibold">${booking.service_name || 'Service'}</div>
              <small class="text-muted">${booking.service_id || ''}</small>
            </div>
          </div>
        </td>
        <td>
          <div class="d-flex align-items-center">
            <img src="https://api.dicebear.com/7.x/avataaars/svg?seed=Provider&backgroundColor=ffd93d" 
                 class="rounded-circle me-2" width="24" alt="Provider">
            <span>Provider</span>
          </div>
        </td>
        <td>
          <span class="badge bg-${getStatusColor(booking.status)}">${booking.status}</span>
        </td>
        <td class="fw-semibold">₹${booking.price || 0}</td>
        <td>
          <div class="small">${formatDate(booking.created_at)}</div>
        </td>
        <td>
          <div class="btn-group btn-group-sm">
            <button class="btn btn-outline-primary btn-sm" onclick="viewBooking('${booking.id}')" title="View Details">
              <i class="fas fa-eye"></i>
            </button>
            ${booking.status === 'In Progress' || booking.status === 'Accepted' ? `
              <button class="btn btn-outline-success btn-sm" onclick="trackProvider('${booking.id}')" title="Track Provider">
                <i class="fas fa-map-marker-alt"></i>
              </button>
            ` : ''}
            ${booking.status === 'Completed' && !booking.rating ? `
              <button class="btn btn-outline-warning btn-sm" onclick="rateBooking('${booking.id}')" title="Rate Service">
                <i class="fas fa-star"></i>
              </button>
            ` : ''}
            ${booking.status === 'Completed' && booking.rating ? `
              <span class="badge bg-success">Rated ${booking.rating}/5</span>
            ` : ''}
            ${booking.status === 'Completed' && booking.rating && !booking.has_payment ? `
              <button class="btn btn-outline-primary btn-sm" onclick="makePayment('${booking.id}')" title="Make Payment">
                <i class="fas fa-credit-card"></i>
              </button>
            ` : ''}
            ${booking.status === 'Completed' && booking.has_payment ? `
              <span class="badge bg-${booking.payment_status === 'Success' ? 'success' : 'warning'}">${booking.payment_status}</span>
            ` : ''}
            ${booking.status === 'Completed' ? `
              <button class="btn btn-outline-info btn-sm" onclick="viewCompletion('${booking.id}')" title="View Completion">
                <i class="fas fa-check-circle"></i>
              </button>
            ` : ''}
          </div>
        </td>
      `;
      tbody.appendChild(row);
    });
  }

  // Initialize map
  async function initializeMap() {
    // Load Google Maps API if not already loaded
    if (typeof google === 'undefined') {
      const script = document.createElement('script');
      script.src = `https://maps.googleapis.com/maps/api/js?key=AIzaSyAG0GnKSwNcd_HtC1x1xVdzf-aWtzTIGBs&callback=initGoogleMap`;
      script.async = true;
      script.defer = true;
      document.head.appendChild(script);
      window.initGoogleMap = () => {
        createGoogleMap();
      };
    } else {
      createGoogleMap();
    }
  }

  function createGoogleMap() {
    const mapOptions = {
      center: { lat: 28.6139, lng: 77.2090 },
      zoom: 12,
      mapTypeId: google.maps.MapTypeId.ROADMAP
    };
    
    map = new google.maps.Map(document.getElementById('map'), mapOptions);

    // Get user location
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(async pos => {
          userLat = pos.coords.latitude;
          userLon = pos.coords.longitude;
          
          // Add user location marker
          window.userLocationMarker = new google.maps.Circle({
            center: { lat: userLat, lng: userLon },
            radius: 50, // 50 meters radius
            strokeColor: '#0d6efd',
            strokeOpacity: 0.8,
            strokeWeight: 2,
            fillColor: '#0d6efd',
            fillOpacity: 0.3,
            map: map
          });
          
          // Add info window for user location
          const infoWindow = new google.maps.InfoWindow({
            content: 'Your location'
          });
          
          window.userLocationMarker.addListener('click', () => {
            infoWindow.open(map, window.userLocationMarker);
          });
          
          map.setCenter({ lat: userLat, lng: userLon });
          map.setZoom(13);
          document.getElementById('locationStatus').textContent = 'Location detected';
          await loadNearbyProviders();
        }, () => {
          document.getElementById('locationStatus').textContent = 'Location access denied';
          await loadNearbyProviders();
        });
    } else {
        document.getElementById('locationStatus').textContent = 'Location not supported';
        await loadNearbyProviders();
      }
  }

  // Load nearby providers
  async function loadNearbyProviders() {
    try {
      const lat = userLat || 28.6139;
      const lon = userLon || 77.2090;
      
      const response = await fetch(`/providers/nearby?lat=${lat}&lon=${lon}&radius=15`);
      providers = await response.json();
      renderProvidersOnMap(providers);
    } catch (error) {
      console.error('Error loading providers:', error);
      // Fallback to dummy data
      providers = [
        { id: 1, name: 'Aarya Electric', skills: ['Electrician'], rating: 4.8, price: 500, lat: 28.62, lon: 77.21 },
        { id: 2, name: 'Pro Plumb', skills: ['Plumber'], rating: 4.6, price: 450, lat: 28.60, lon: 77.19 },
        { id: 3, name: 'WoodWorks', skills: ['Carpenter'], rating: 4.7, price: 600, lat: 28.59, lon: 77.22 },
        { id: 4, name: 'Shine Clean', skills: ['Cleaner'], rating: 4.5, price: 300, lat: 28.61, lon: 77.17 },
      ];
      renderProvidersOnMap(providers);
    }
  }

  // Render providers on map
  function renderProvidersOnMap(providers) {
    // Clear existing markers
    if (window.providerMarkers) {
      window.providerMarkers.forEach(marker => marker.setMap(null));
    }
    window.providerMarkers = [];

    let nearest = null;
    let nearestDist = Infinity;

    providers.forEach(provider => {
      const marker = new google.maps.Marker({
        position: { lat: provider.lat, lng: provider.lon },
        map: map,
        title: provider.name
      });
      
      const popupContent = `
        <div class="provider-popup">
          <div class="d-flex align-items-center mb-2">
            <img src="https://api.dicebear.com/7.x/avataaars/svg?seed=${provider.name}&backgroundColor=ffd93d" 
                 class="rounded-circle me-2" width="40" alt="${provider.name}">
            <div>
              <h6 class="mb-0 fw-bold">${provider.name}</h6>
              <div class="rating">
                <i class="fas fa-star text-warning"></i>
                <span class="ms-1">${provider.rating}</span>
              </div>
            </div>
          </div>
          <div class="mb-2">
            <small class="text-muted">Skills:</small>
            <div class="skills mt-1">
              ${provider.skills.map(skill => `<span class="badge bg-light text-dark me-1">${skill}</span>`).join('')}
            </div>
          </div>
          <div class="d-flex justify-content-between align-items-center">
            <span class="fw-bold text-primary">₹${provider.price}/hr</span>
            <a href="/booking-map?provider_id=${provider.id}" class="btn btn-primary btn-sm">Book</a>
          </div>
        </div>
      `;
      
      const infoWindow = new google.maps.InfoWindow({
        content: popupContent
      });
      
      marker.addListener('click', () => {
        infoWindow.open(map, marker);
      });
      
      window.providerMarkers.push(marker);
      
      // Check if nearest
      if (userLat && userLon) {
        const distance = calculateDistance(userLat, userLon, provider.lat, provider.lon);
        if (distance < nearestDist) {
          nearestDist = distance;
          nearest = marker;
        }
      }
    });

    // Highlight nearest provider
    if (nearest) {
      nearest.bindTooltip('Nearest', {
        permanent: true,
        className: 'badge bg-success text-wrap'
      }).openTooltip();
    }
  }

  // Setup event listeners
  function setupEventListeners() {
    // Refresh providers button
    document.getElementById('refreshProviders')?.addEventListener('click', loadNearbyProviders);
    
    // Booking filter buttons
    document.querySelectorAll('input[name="bookingFilter"]').forEach(radio => {
      radio.addEventListener('change', function() {
        filterBookings(this.id);
      });
    });
  }

  // Filter bookings
  function filterBookings(filterId) {
    let filteredBookings = userBookings;
    
    switch(filterId) {
      case 'activeBookings':
        filteredBookings = userBookings.filter(b => ['Pending', 'Accepted', 'In Progress'].includes(b.status));
        break;
      case 'completedBookings':
        filteredBookings = userBookings.filter(b => b.status === 'Completed');
        break;
    }
    
    renderUserBookings(filteredBookings);
  }

  // Utility functions
  function calculateDistance(lat1, lon1, lat2, lon2) {
    const dx = (lat2 - lat1);
    const dy = (lon2 - lon1);
    return Math.sqrt(dx * dx + dy * dy) * 111;
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

  // Update provider location on map
  function updateProviderLocation(data) {
    // Update provider marker if it exists
    map.eachLayer(layer => {
      if (layer instanceof L.Marker && layer.providerId === data.user_id) {
        layer.setLatLng([data.lat, data.lon]);
        layer.bindPopup(`
          <div class="provider-popup">
            <div class="d-flex align-items-center mb-2">
              <img src="https://api.dicebear.com/7.x/avataaars/svg?seed=${data.name}&backgroundColor=ffd93d" 
                   class="rounded-circle me-2" width="40" alt="${data.name}">
              <div>
                <h6 class="mb-0 fw-bold">${data.name}</h6>
                <div class="rating">
                  <i class="fas fa-star text-warning"></i>
                  <span class="ms-1">${data.rating}</span>
                </div>
              </div>
            </div>
            <div class="mb-2">
              <small class="text-success"><i class="fas fa-circle"></i> Live Location</small>
            </div>
            <div class="d-flex justify-content-between align-items-center">
              <span class="fw-bold text-primary">Active</span>
              <button class="btn btn-primary btn-sm" onclick="window.open('/track-provider?provider_id=${data.user_id}', '_blank')">Track</button>
            </div>
          </div>
        `);
      }
    });
  }

  // Show notification
  function showNotification(message, type = 'info') {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
    notification.style.cssText = 'top: 80px; right: 20px; z-index: 9999; min-width: 300px;';
    notification.innerHTML = `
      ${message}
      <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    document.body.appendChild(notification);
    
    // Auto remove after 5 seconds
    setTimeout(() => {
      if (notification.parentNode) {
        notification.remove();
      }
    }, 5000);
  }

  // Global functions for buttons
  window.viewBooking = function(bookingId) {
    // Find booking details
    const booking = userBookings.find(b => b.id === bookingId);
    if (!booking) return;

    // Create modal
    const modal = document.createElement('div');
    modal.className = 'modal fade';
    modal.innerHTML = `
      <div class="modal-dialog modal-lg">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">Booking Details</h5>
            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
          </div>
          <div class="modal-body">
            <div class="row g-3">
              <div class="col-md-6">
                <h6>Service</h6>
                <p class="text-muted">${booking.service_name || 'Service'}</p>
              </div>
              <div class="col-md-6">
                <h6>Status</h6>
                <span class="badge bg-${getStatusColor(booking.status)}">${booking.status}</span>
              </div>
              <div class="col-md-6">
                <h6>Price</h6>
                <p class="fw-bold text-primary">₹${booking.price || 0}</p>
              </div>
              <div class="col-md-6">
                <h6>Date</h6>
                <p class="text-muted">${formatDate(booking.created_at)}</p>
              </div>
              ${booking.notes ? `
                <div class="col-12">
                  <h6>Notes</h6>
                  <p class="text-muted">${booking.notes}</p>
                </div>
              ` : ''}
            </div>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
          </div>
        </div>
      </div>
    `;
    
    document.body.appendChild(modal);
    const bsModal = new bootstrap.Modal(modal);
    bsModal.show();
    
    // Remove modal after hiding
    modal.addEventListener('hidden.bs.modal', () => modal.remove());
  };

  window.trackProvider = function(bookingId) {
    // Find booking details
    const booking = userBookings.find(b => b.id === bookingId);
    if (!booking || !booking.provider_id) {
      showNotification('Provider information not available', 'warning');
      return;
    }

    // Open tracking page
    window.open(`/track-provider?provider_id=${booking.provider_id}&booking_id=${bookingId}`, '_blank');
  };

  window.rateBooking = function(bookingId) {
    // Find booking details
    const booking = userBookings.find(b => b.id === bookingId);
    if (!booking) return;

    // Create rating modal
    const modal = document.createElement('div');
    modal.className = 'modal fade';
    modal.innerHTML = `
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">Rate Your Service</h5>
            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
          </div>
          <div class="modal-body">
            <div class="text-center mb-4">
              <h6>${booking.service_name || 'Service'}</h6>
              <p class="text-muted">How was your experience?</p>
            </div>
            <div class="rating-stars text-center mb-4">
              <div class="stars" style="font-size: 2rem;">
                <i class="far fa-star star" data-rating="1"></i>
                <i class="far fa-star star" data-rating="2"></i>
                <i class="far fa-star star" data-rating="3"></i>
                <i class="far fa-star star" data-rating="4"></i>
                <i class="far fa-star star" data-rating="5"></i>
              </div>
              <p class="mt-2 text-muted small">Click to rate</p>
            </div>
            <div class="form-floating">
              <textarea class="form-control" placeholder="Leave a review..." id="reviewText" style="height: 100px"></textarea>
              <label for="reviewText">Review (Optional)</label>
            </div>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
            <button type="button" class="btn btn-primary" id="submitRating" disabled>Submit Rating</button>
          </div>
        </div>
      </div>
    `;
    
    document.body.appendChild(modal);
    const bsModal = new bootstrap.Modal(modal);
    bsModal.show();
    
    let selectedRating = 0;
    
    // Handle star clicks
    modal.querySelectorAll('.star').forEach(star => {
      star.addEventListener('click', function() {
        selectedRating = parseInt(this.dataset.rating);
        
        // Update star display
        modal.querySelectorAll('.star').forEach((s, index) => {
          if (index < selectedRating) {
            s.className = 'fas fa-star star text-warning';
          } else {
            s.className = 'far fa-star star text-warning';
          }
        });
        
        // Enable submit button
        modal.querySelector('#submitRating').disabled = false;
      });
      
      star.addEventListener('mouseenter', function() {
        const rating = parseInt(this.dataset.rating);
        modal.querySelectorAll('.star').forEach((s, index) => {
          if (index < rating) {
            s.className = 'fas fa-star star text-warning';
          } else {
            s.className = 'far fa-star star text-warning';
          }
        });
      });
    });
    
    // Handle submit rating
    modal.querySelector('#submitRating').addEventListener('click', async function() {
      if (selectedRating === 0) return;
      
      try {
        const token = localStorage.getItem('token');
        const response = await fetch(`/bookings/${bookingId}/rate`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
          },
          body: JSON.stringify({
            rating: selectedRating,
            review: modal.querySelector('#reviewText').value
          })
        });
        
        if (response.ok) {
          showNotification('Thank you for your rating!', 'success');
          bsModal.hide();
          loadUserBookings(); // Refresh bookings
          loadUserData(); // Refresh stats
        } else {
          showNotification('Failed to submit rating', 'danger');
        }
      } catch (error) {
        console.error('Error submitting rating:', error);
        showNotification('Failed to submit rating', 'danger');
      }
    });
    
    // Remove modal after hiding
    modal.addEventListener('hidden.bs.modal', () => modal.remove());
  };

  window.makePayment = async function(bookingId) {
    // Find booking details
    const booking = userBookings.find(b => b.id === bookingId);
    if (!booking) return;

    try {
      const token = localStorage.getItem('token');
      
      // Create Razorpay order
      const response = await fetch('/payments/razorpay/create-order', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ booking_id: bookingId })
      });

      if (!response.ok) {
        throw new Error('Failed to create payment order');
      }

      const orderData = await response.json();

      // Configure Razorpay options
      const options = {
        key: orderData.key,
        amount: orderData.amount,
        currency: orderData.currency,
        name: 'HooFix',
        description: `Payment for ${booking.service_name}`,
        order_id: orderData.order_id,
        handler: async function(response) {
          try {
            // Verify payment
            const verifyResponse = await fetch('/payments/razorpay/verify', {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
              },
              body: JSON.stringify({
                payment_id: orderData.payment_id,
                razorpay_payment_id: response.razorpay_payment_id,
                razorpay_signature: response.razorpay_signature
              })
            });

            if (verifyResponse.ok) {
              showNotification('Payment successful!', 'success');
              loadUserBookings(); // Refresh bookings
            } else {
              showNotification('Payment verification failed', 'danger');
            }
          } catch (error) {
            console.error('Error verifying payment:', error);
            showNotification('Payment verification failed', 'danger');
          }
        },
        prefill: {
          name: 'User',
          email: 'user@example.com',
          contact: '9999999999'
        },
        theme: {
          color: '#0d6efd'
        }
      };

      // Open Razorpay checkout
      const rzp = new Razorpay(options);
      rzp.open();

    } catch (error) {
      console.error('Error creating payment:', error);
      showNotification('Failed to initiate payment', 'danger');
    }
  };

  window.viewCompletion = async function(bookingId) {
    // Find booking details
    const booking = userBookings.find(b => b.id === bookingId);
    if (!booking) return;

    try {
      const token = localStorage.getItem('token');
      
      // Get completion details
      const response = await fetch(`/completion/${bookingId}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (!response.ok) {
        throw new Error('Failed to load completion details');
      }

      const completionData = await response.json();

      // Create modal
      const modal = document.createElement('div');
      modal.className = 'modal fade';
      modal.innerHTML = `
        <div class="modal-dialog modal-lg">
          <div class="modal-content">
            <div class="modal-header">
              <h5 class="modal-title">Service Completion Details</h5>
              <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <div class="modal-body">
              <div class="row g-3">
                <div class="col-12">
                  <h6>Service: ${booking.service_name || 'Service'}</h6>
                  <p class="text-muted">Completed on ${completionData.completed_at ? new Date(completionData.completed_at).toLocaleDateString() : 'N/A'}</p>
                </div>
                ${completionData.completion_notes ? `
                  <div class="col-12">
                    <h6>Completion Notes</h6>
                    <div class="card">
                      <div class="card-body">
                        <p class="mb-0">${completionData.completion_notes}</p>
                      </div>
                    </div>
                  </div>
                ` : ''}
                ${completionData.completion_images && completionData.completion_images.length > 0 ? `
                  <div class="col-12">
                    <h6>Completion Images</h6>
                    <div class="row g-2">
                      ${completionData.completion_images.map(image => `
                        <div class="col-md-4">
                          <img src="/static/${image}" class="img-fluid rounded" alt="Completion Image" 
                               style="height: 150px; object-fit: cover; width: 100%;">
                        </div>
                      `).join('')}
                    </div>
                  </div>
                ` : ''}
                <div class="col-12">
                  <h6>Payment Status</h6>
                  <span class="badge bg-${booking.payment_status === 'Success' ? 'success' : 'warning'}">
                    ${booking.payment_status || 'Pending'}
                  </span>
                </div>
              </div>
            </div>
            <div class="modal-footer">
              <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
              ${!booking.has_payment ? `
                <button type="button" class="btn btn-primary" onclick="makePayment('${bookingId}')">
                  <i class="fas fa-credit-card me-2"></i>Make Payment
                </button>
              ` : ''}
            </div>
          </div>
        </div>
      `;
      
      document.body.appendChild(modal);
      const bsModal = new bootstrap.Modal(modal);
      bsModal.show();
      
      // Remove modal after hiding
      modal.addEventListener('hidden.bs.modal', () => modal.remove());

    } catch (error) {
      console.error('Error loading completion details:', error);
      showNotification('Failed to load completion details', 'danger');
    }
  };

})();

