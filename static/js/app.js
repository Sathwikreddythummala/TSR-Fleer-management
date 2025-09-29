// static/js/app.js

// Helper function to create hidden inputs
function createHiddenInput(form, name, value) {
    const input = document.createElement('input');
    input.type = 'hidden';
    input.name = name;
    input.value = value;
    form.appendChild(input);
}

// Toggle fields based on category selection
function toggleCategoryFields() {
    const categorySelect = document.getElementById('category');
    const dieselFields = document.getElementById('dieselFields');
    const salaryFields = document.getElementById('salaryFields');
    const othersFields = document.getElementById('othersFields');
    
    // Hide all category sections first
    dieselFields.classList.add('hidden');
    salaryFields.classList.add('hidden');
    othersFields.classList.add('hidden');
    
    // Show the selected category section
    if (categorySelect.value === 'diesel') {
        dieselFields.classList.remove('hidden');
        toggleDieselFields();
    } else if (categorySelect.value === 'salary') {
        salaryFields.classList.remove('hidden');
    } else if (categorySelect.value === 'others') {
        othersFields.classList.remove('hidden');
    }
}

// Toggle diesel fields based on payment status
function toggleDieselFields() {
    const dieselPayment = document.getElementById('diesel_payment_status');
    const paidDieselFields = document.getElementById('paidDieselFields');
    const unpaidDieselFields = document.getElementById('unpaidDieselFields');
    
    if (dieselPayment.value === 'Paid') {
        paidDieselFields.classList.remove('hidden');
        unpaidDieselFields.classList.add('hidden');
    } else {
        paidDieselFields.classList.add('hidden');
        unpaidDieselFields.classList.remove('hidden');
    }
}

// Switch between paid and unpaid tabs
function switchTab(tabId) {
    // Hide all tab contents
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
    });
    
    // Show the selected tab content
    document.getElementById(tabId).classList.add('active');
    
    // Update tab buttons
    document.querySelectorAll('.tab').forEach(tab => {
        tab.classList.remove('active');
    });
    
    // Find the clicked tab and activate it
    const tabs = document.querySelectorAll('.tab');
    for (let tab of tabs) {
        if (tab.onclick && tab.onclick.toString().includes(tabId)) {
            tab.classList.add('active');
            break;
        }
    }
}

// Function to load vehicle spendings
function loadVehicleSpendings(vehicleId, month){
  fetch(`/vehicle_spendings/${vehicleId}?month=${month}`)
    .then(r => r.json())
    .then(rows => {
      const area = document.getElementById('vehicleSpendingsList');
      let html = '<h4>Spendings</h4>';
      if(!rows || rows.length === 0){
        html += '<p>No spendings found for selected month.</p>';
      } else {
        html += '<table class="spend-table"><thead><tr><th>Date</th><th>Category</th><th>Reason</th><th>Amount</th><th>Status</th><th>Marked</th></tr></thead><tbody>';
        rows.forEach(r=>{
          const status = (r.spended_by && r.mode) ? 'Paid' : 'Unpaid';
          html += `<tr class="${r.marked ? 'marked' : ''}"><td>${r.date}</td><td>${r.category}</td><td>${r.reason || ''}</td><td>₹${parseFloat(r.amount).toFixed(2)}</td><td>${status}</td><td>${r.marked ? 'Yes':'No'}</td></tr>`;
        });
        html += '</tbody></table>';
      }
      area.innerHTML = html;
    });
}

// Toggle mark function
function toggleMark(id) {
    const tr = document.querySelector(`tr[data-id="${id}"]`);
    fetch('/toggle_mark', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({id: id})
    }).then(r => r.json()).then(data => {
        if(data.success){
            tr.classList.toggle('marked');
        } else {
            alert('Failed to toggle mark');
        }
    });
}

// Mark unpaid payment as paid
function markAsPaid(id) {
    if(confirm('Are you sure you want to mark this payment as paid?')) {
        fetch('/mark_paid/' + id, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                spended_by: 'TSR', // Default value
                mode: 'Cash' // Default value
            })
        })
        .then(r => r.json())
        .then(data => {
            if(data.success){
                alert('Payment marked as paid successfully');
                location.reload();
            } else {
                alert('Failed to mark payment as paid: ' + (data.message || 'Unknown error'));
            }
        })
        .catch(err => {
            console.error('Error:', err);
            alert('An error occurred while marking payment as paid');
        });
    }
}

// Main DOM content loaded event
document.addEventListener('DOMContentLoaded', function(){
  // mark/unmark checkboxes on spendings page
  document.querySelectorAll('.mark-checkbox').forEach(function(cb){
    cb.addEventListener('change', function(e){
      const tr = e.target.closest('tr');
      const id = tr.dataset.id;
      fetch('/toggle_mark', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({id: id})
      }).then(r => r.json()).then(data => {
        if(data.success){
          tr.classList.toggle('marked');
        } else {
          alert('Failed to toggle mark');
        }
      });
    });
  });

  // vehicle buttons load monthly spendings
  const vehicleButtons = document.querySelectorAll('.veh-btn');
  if(vehicleButtons){
    vehicleButtons.forEach(btn=>{
      btn.addEventListener('click', function(){
        const vid = this.dataset.id;
        const monthInput = document.getElementById('vehicleMonth');
        const month = monthInput ? monthInput.value : '';
        loadVehicleSpendings(vid, month);
      });
    });
  }

  const loadBtn = document.getElementById('loadVehicleSpend');
  if(loadBtn){
    loadBtn.addEventListener('click', function(){
      const month = document.getElementById('vehicleMonth').value;
      const activeBtn = document.querySelector('.veh-btn.active');
      const vid = activeBtn ? activeBtn.dataset.id : null;
      if(!vid){
        alert('Click a vehicle button first');
        return;
      }
      loadVehicleSpendings(vid, month);
    });
  }

  // Edit button functionality
  document.querySelectorAll('.btn-edit').forEach(function(btn){
    btn.addEventListener('click', function(e){
      const id = this.dataset.id;
      alert('Edit functionality for spending ID: ' + id + ' will be implemented soon.');
      // TODO: Implement edit modal or form
    });
  });

  // Delete button functionality
  document.querySelectorAll('.btn-delete').forEach(function(btn){
    btn.addEventListener('click', function(e){
      const id = this.dataset.id;
      if(confirm('Are you sure you want to delete this spending?')) {
        fetch('/delete_spending/' + id, {
          method: 'DELETE'
        }).then(r => r.json()).then(data => {
          if(data.success){
            location.reload();
          } else {
            alert('Failed to delete spending');
          }
        });
      }
    });
  });

  // Mark as paid button functionality
  document.querySelectorAll('.btn-mark-paid').forEach(function(btn){
    btn.addEventListener('click', function(e){
      const id = this.dataset.id;
      markAsPaid(id);
    });
  });

  // Show duplicate warning if needed
  const urlParams = new URLSearchParams(window.location.search);
  if(urlParams.get('duplicate') === 'true') {
    alert('This spending entry already exists. Please check for duplicates.');
  }

  // Toggle fields based on category selection
  const categorySelect = document.getElementById('category');
  if (categorySelect) {
    categorySelect.addEventListener('change', toggleCategoryFields);
    
    // Initialize category fields
    toggleCategoryFields();
  }

  // Diesel payment status change
  const dieselPaymentStatus = document.getElementById('diesel_payment_status');
  if (dieselPaymentStatus) {
    dieselPaymentStatus.addEventListener('change', toggleDieselFields);
    // Initialize diesel fields
    toggleDieselFields();
  }

  // Salary and Others category fields - ensure they show paid fields by default
  const salaryFields = document.getElementById('salaryFields');
  const othersFields = document.getElementById('othersFields');
  if (salaryFields) salaryFields.classList.remove('hidden');
  if (othersFields) othersFields.classList.remove('hidden');

  // Spending form submission
  const spendingForm = document.getElementById('spendingForm');
  if (spendingForm) {
    spendingForm.addEventListener('submit', function(e) {
      const category = document.getElementById('category').value;
      
      // Clear any previous hidden inputs
      document.querySelectorAll('[name="amount"], [name="spended_by"], [name="mode"], [name="reason"]').forEach(input => {
        if (input.type === 'hidden') {
          input.remove();
        }
      });
      
      // Create hidden inputs for the actual values to be submitted
      if (category === 'diesel') {
        const paymentStatus = document.getElementById('diesel_payment_status').value;
        const reason = 'Diesel - ' + paymentStatus;
        
        // Create hidden input for reason
        createHiddenInput(this, 'reason', reason);
        
        if (paymentStatus === 'Paid') {
          const amount = document.getElementById('diesel_amount').value;
          const spendedBy = document.getElementById('diesel_spended_by').value;
          const mode = document.getElementById('diesel_mode').value;
          
          // Create hidden inputs for paid spending
          createHiddenInput(this, 'amount', amount);
          createHiddenInput(this, 'spended_by', spendedBy);
          createHiddenInput(this, 'mode', mode);
        } else {
          const unpaidAmount = document.getElementById('unpaid_diesel_amount').value;
          // For unpaid spending, only create amount input (spended_by and mode will be NULL)
          createHiddenInput(this, 'amount', unpaidAmount);
          // Explicitly set spended_by and mode to empty strings so they become NULL
          createHiddenInput(this, 'spended_by', '');
          createHiddenInput(this, 'mode', '');
        }
      } 
      else if (category === 'salary') {
        const amount = document.getElementById('salary_amount').value;
        const spendedBy = document.getElementById('salary_spended_by').value;
        const mode = document.getElementById('salary_mode').value;
        const reason = 'Driver Salary';
        
        createHiddenInput(this, 'amount', amount);
        createHiddenInput(this, 'spended_by', spendedBy);
        createHiddenInput(this, 'mode', mode);
        createHiddenInput(this, 'reason', reason);
      } 
      else if (category === 'others') {
        const reason = document.getElementById('reason').value;
        const amount = document.getElementById('others_amount').value;
        const spendedBy = document.getElementById('others_spended_by').value;
        const mode = document.getElementById('others_mode').value;
        
        createHiddenInput(this, 'amount', amount);
        createHiddenInput(this, 'spended_by', spendedBy);
        createHiddenInput(this, 'mode', mode);
        createHiddenInput(this, 'reason', reason);
      }
      
      // Form validation
      let isValid = true;
      let errorMessage = '';
      
      const amountInput = document.querySelector('input[name="amount"]');
      if (!amountInput || !amountInput.value || parseFloat(amountInput.value) <= 0) {
        isValid = false;
        errorMessage = 'Please enter a valid amount';
      }
      
      if (category === 'others') {
        const reasonInput = document.querySelector('input[name="reason"]');
        if (!reasonInput || !reasonInput.value.trim()) {
          isValid = false;
          errorMessage = 'Please enter a reason for the spending';
        }
      }
      
      if (!isValid) {
        e.preventDefault();
        alert(errorMessage);
      }
    });
  }

  // Add to app.js

// Settlement modal functions
function openModal() {
    document.getElementById('settlementModal').style.display = 'flex';
}

function closeModal() {
    document.getElementById('settlementModal').style.display = 'none';
}

// Close modal when clicking outside of it
window.onclick = function(event) {
    const modal = document.getElementById('settlementModal');
    if (event.target === modal) {
        closeModal();
    }
}

// Add this to your DOMContentLoaded event in app.js
document.addEventListener('DOMContentLoaded', function() {
    // ... existing code ...
    
    // Settlement button event listener
    const makeSettlementBtn = document.getElementById('makeSettlementBtn');
    if (makeSettlementBtn) {
        makeSettlementBtn.addEventListener('click', openModal);
    }
    
    // Close modal button
    const closeBtn = document.querySelector('.close');
    if (closeBtn) {
        closeBtn.addEventListener('click', closeModal);
    }
    
    // Select all checkbox functionality
    const selectAllCheckbox = document.getElementById('selectAllUnpaid');
    if (selectAllCheckbox) {
        selectAllCheckbox.addEventListener('change', function() {
            const checkboxes = document.querySelectorAll('.unpaid-checkbox');
            checkboxes.forEach(checkbox => {
                checkbox.checked = this.checked;
            });
            updateSettlementSummary();
        });
    }
    
    // Individual checkbox functionality
    const checkboxes = document.querySelectorAll('.unpaid-checkbox');
    checkboxes.forEach(checkbox => {
        checkbox.addEventListener('change', updateSettlementSummary);
    });
    
    // Settlement form submission
    const settlementForm = document.getElementById('settlementForm');
    if (settlementForm) {
        settlementForm.addEventListener('submit', function(e) {
            e.preventDefault();
            processSettlement();
        });
    }
});

function updateSettlementSummary() {
    const selectedCheckboxes = document.querySelectorAll('.unpaid-checkbox:checked');
    let total = 0;
    
    selectedCheckboxes.forEach(checkbox => {
        total += parseFloat(checkbox.dataset.amount);
    });
    
    document.getElementById('selectedCount').textContent = selectedCheckboxes.length;
    document.getElementById('selectedTotal').textContent = total.toFixed(2);
}

function processSettlement() {
    const selectedCheckboxes = document.querySelectorAll('.unpaid-checkbox:checked');
    const spendingIds = Array.from(selectedCheckboxes).map(checkbox => checkbox.dataset.id);
    const spendedBy = document.getElementById('settlement_spended_by').value;
    const mode = document.getElementById('settlement_mode').value;
    
    if (spendingIds.length === 0) {
        alert('Please select at least one payment to settle.');
        return;
    }
    
    fetch('/process_settlement', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            spending_ids: spendingIds,
            spended_by: spendedBy,
            mode: mode
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alert(data.message);
            closeModal();
            location.reload();
        } else {
            alert('Error: ' + (data.message || 'Unknown error'));
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('An error occurred while processing the settlement.');
    });
}

// static/js/app.js

// Helper function to create hidden inputs
function createHiddenInput(form, name, value) {
    const input = document.createElement('input');
    input.type = 'hidden';
    input.name = name;
    input.value = value;
    form.appendChild(input);
}

// Toggle fields based on category selection
function toggleCategoryFields() {
    const categorySelect = document.getElementById('category');
    const dieselFields = document.getElementById('dieselFields');
    const salaryFields = document.getElementById('salaryFields');
    const othersFields = document.getElementById('othersFields');
    
    // Hide all category sections first
    dieselFields.classList.add('hidden');
    salaryFields.classList.add('hidden');
    othersFields.classList.add('hidden');
    
    // Show the selected category section
    if (categorySelect.value === 'diesel') {
        dieselFields.classList.remove('hidden');
        toggleDieselFields();
    } else if (categorySelect.value === 'salary') {
        salaryFields.classList.remove('hidden');
    } else if (categorySelect.value === 'others') {
        othersFields.classList.remove('hidden');
    }
}

// Toggle diesel fields based on payment status
function toggleDieselFields() {
    const dieselPayment = document.getElementById('diesel_payment_status');
    const paidDieselFields = document.getElementById('paidDieselFields');
    const unpaidDieselFields = document.getElementById('unpaidDieselFields');
    
    if (dieselPayment.value === 'Paid') {
        paidDieselFields.classList.remove('hidden');
        unpaidDieselFields.classList.add('hidden');
    } else {
        paidDieselFields.classList.add('hidden');
        unpaidDieselFields.classList.remove('hidden');
    }
}

// Switch between paid and unpaid tabs
function switchTab(tabId) {
    // Hide all tab contents
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
    });
    
    // Show the selected tab content
    document.getElementById(tabId).classList.add('active');
    
    // Update tab buttons
    document.querySelectorAll('.tab').forEach(tab => {
        tab.classList.remove('active');
    });
    
    // Find the clicked tab and activate it
    const tabs = document.querySelectorAll('.tab');
    for (let tab of tabs) {
        if (tab.onclick && tab.onclick.toString().includes(tabId)) {
            tab.classList.add('active');
            break;
        }
    }
}

// Function to load vehicle spendings
function loadVehicleSpendings(vehicleId, month){
  fetch(`/vehicle_spendings/${vehicleId}?month=${month}`)
    .then(r => r.json())
    .then(rows => {
      const area = document.getElementById('vehicleSpendingsList');
      let html = '<h4>Spendings</h4>';
      if(!rows || rows.length === 0){
        html += '<p>No spendings found for selected month.</p>';
      } else {
        html += '<table class="spend-table"><thead><tr><th>Date</th><th>Category</th><th>Reason</th><th>Amount</th><th>Status</th><th>Marked</th></tr></thead><tbody>';
        rows.forEach(r=>{
          const status = (r.spended_by && r.mode) ? 'Paid' : 'Unpaid';
          html += `<tr class="${r.marked ? 'marked' : ''}"><td>${r.date}</td><td>${r.category}</td><td>${r.reason || ''}</td><td>₹${parseFloat(r.amount).toFixed(2)}</td><td>${status}</td><td>${r.marked ? 'Yes':'No'}</td></tr>`;
        });
        html += '</tbody></table>';
      }
      area.innerHTML = html;
    });
}

// Toggle mark function
function toggleMark(id) {
    const tr = document.querySelector(`tr[data-id="${id}"]`);
    fetch('/toggle_mark', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({id: id})
    }).then(r => r.json()).then(data => {
        if(data.success){
            tr.classList.toggle('marked');
        } else {
            alert('Failed to toggle mark');
        }
    });
}

// Mark unpaid payment as paid
function markAsPaid(id) {
    if(confirm('Are you sure you want to mark this payment as paid?')) {
        fetch('/mark_paid/' + id, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                spended_by: 'TSR', // Default value
                mode: 'Cash' // Default value
            })
        })
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(data => {
            if(data.success){
                alert('Payment marked as paid successfully');
                location.reload();
            } else {
                alert('Failed to mark payment as paid: ' + (data.message || 'Unknown error'));
            }
        })
        .catch(err => {
            console.error('Error:', err);
            alert('An error occurred while marking payment as paid. Check console for details.');
        });
    }
}

// Main DOM content loaded event
document.addEventListener('DOMContentLoaded', function(){
  // mark/unmark checkboxes on spendings page
  document.querySelectorAll('.mark-checkbox').forEach(function(cb){
    cb.addEventListener('change', function(e){
      const tr = e.target.closest('tr');
      const id = tr.dataset.id;
      fetch('/toggle_mark', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({id: id})
      }).then(r => r.json()).then(data => {
        if(data.success){
          tr.classList.toggle('marked');
        } else {
          alert('Failed to toggle mark');
        }
      });
    });
  });

  // vehicle buttons load monthly spendings
  const vehicleButtons = document.querySelectorAll('.veh-btn');
  if(vehicleButtons){
    vehicleButtons.forEach(btn=>{
      btn.addEventListener('click', function(){
        const vid = this.dataset.id;
        const monthInput = document.getElementById('vehicleMonth');
        const month = monthInput ? monthInput.value : '';
        loadVehicleSpendings(vid, month);
      });
    });
  }

  const loadBtn = document.getElementById('loadVehicleSpend');
  if(loadBtn){
    loadBtn.addEventListener('click', function(){
      const month = document.getElementById('vehicleMonth').value;
      const activeBtn = document.querySelector('.veh-btn.active');
      const vid = activeBtn ? activeBtn.dataset.id : null;
      if(!vid){
        alert('Click a vehicle button first');
        return;
      }
      loadVehicleSpendings(vid, month);
    });
  }

  // Delete button functionality
  document.querySelectorAll('.btn-delete').forEach(function(btn){
    btn.addEventListener('click', function(e){
      const id = this.dataset.id;
      if(confirm('Are you sure you want to delete this spending?')) {
        fetch('/delete_spending/' + id, {
          method: 'DELETE'
        }).then(r => r.json()).then(data => {
          if(data.success){
            location.reload();
          } else {
            alert('Failed to delete spending');
          }
        });
      }
    });
  });

  // Show duplicate warning if needed
  const urlParams = new URLSearchParams(window.location.search);
  if(urlParams.get('duplicate') === 'true') {
    alert('This spending entry already exists. Please check for duplicates.');
  }

  // Toggle fields based on category selection
  const categorySelect = document.getElementById('category');
  if (categorySelect) {
    categorySelect.addEventListener('change', toggleCategoryFields);
    
    // Initialize category fields
    toggleCategoryFields();
  }

  // Diesel payment status change
  const dieselPaymentStatus = document.getElementById('diesel_payment_status');
  if (dieselPaymentStatus) {
    dieselPaymentStatus.addEventListener('change', toggleDieselFields);
    // Initialize diesel fields
    toggleDieselFields();
  }

  // Salary and Others category fields - ensure they show paid fields by default
  const salaryFields = document.getElementById('salaryFields');
  const othersFields = document.getElementById('othersFields');
  if (salaryFields) salaryFields.classList.remove('hidden');
  if (othersFields) othersFields.classList.remove('hidden');

  // Spending form submission
  const spendingForm = document.getElementById('spendingForm');
  if (spendingForm) {
    spendingForm.addEventListener('submit', function(e) {
      const category = document.getElementById('category').value;
      
      // Clear any previous hidden inputs
      document.querySelectorAll('[name="amount"], [name="spended_by"], [name="mode"], [name="reason"]').forEach(input => {
        if (input.type === 'hidden') {
          input.remove();
        }
      });
      
      // Create hidden inputs for the actual values to be submitted
      if (category === 'diesel') {
        const paymentStatus = document.getElementById('diesel_payment_status').value;
        const reason = 'Diesel - ' + paymentStatus;
        
        // Create hidden input for reason
        createHiddenInput(this, 'reason', reason);
        
        if (paymentStatus === 'Paid') {
          const amount = document.getElementById('diesel_amount').value;
          const spendedBy = document.getElementById('diesel_spended_by').value;
          const mode = document.getElementById('diesel_mode').value;
          
          // Create hidden inputs for paid spending
          createHiddenInput(this, 'amount', amount);
          createHiddenInput(this, 'spended_by', spendedBy);
          createHiddenInput(this, 'mode', mode);
        } else {
          const unpaidAmount = document.getElementById('unpaid_diesel_amount').value;
          // For unpaid spending, only create amount input (spended_by and mode will be NULL)
          createHiddenInput(this, 'amount', unpaidAmount);
          // Explicitly set spended_by and mode to empty strings so they become NULL
          createHiddenInput(this, 'spended_by', '');
          createHiddenInput(this, 'mode', '');
        }
      } 
      else if (category === 'salary') {
        const amount = document.getElementById('salary_amount').value;
        const spendedBy = document.getElementById('salary_spended_by').value;
        const mode = document.getElementById('salary_mode').value;
        const reason = 'Driver Salary';
        
        createHiddenInput(this, 'amount', amount);
        createHiddenInput(this, 'spended_by', spendedBy);
        createHiddenInput(this, 'mode', mode);
        createHiddenInput(this, 'reason', reason);
      } 
      else if (category === 'others') {
        const reason = document.getElementById('reason').value;
        const amount = document.getElementById('others_amount').value;
        const spendedBy = document.getElementById('others_spended_by').value;
        const mode = document.getElementById('others_mode').value;
        
        createHiddenInput(this, 'amount', amount);
        createHiddenInput(this, 'spended_by', spendedBy);
        createHiddenInput(this, 'mode', mode);
        createHiddenInput(this, 'reason', reason);
      }
      
      // Form validation
      let isValid = true;
      let errorMessage = '';
      
      const amountInput = document.querySelector('input[name="amount"]');
      if (!amountInput || !amountInput.value || parseFloat(amountInput.value) <= 0) {
        isValid = false;
        errorMessage = 'Please enter a valid amount';
      }
      
      if (category === 'others') {
        const reasonInput = document.querySelector('input[name="reason"]');
        if (!reasonInput || !reasonInput.value.trim()) {
          isValid = false;
          errorMessage = 'Please enter a reason for the spending';
        }
      }
      
      if (!isValid) {
        e.preventDefault();
        alert(errorMessage);
      }
    });
  }
});

// static/js/app.js
// This file can be used for additional JavaScript functionality

// Function to filter payments based on search input
function filterPayments() {
    const searchText = document.getElementById('searchInput').value.toLowerCase();
    const activeTab = document.querySelector('.tab-content.active').id;
    const table = document.getElementById(activeTab === 'paidTab' ? 'paidTable' : 
                                          activeTab === 'unpaidTab' ? 'unpaidTable' : 
                                          activeTab === 'settledTab' ? 'settledTable' : null);
    
    if (!table) return;
    
    const rows = table.getElementsByTagName('tbody')[0].getElementsByTagName('tr');
    
    for (let i = 0; i < rows.length; i++) {
        const row = rows[i];
        const cells = row.getElementsByTagName('td');
        let found = false;
        
        for (let j = 0; j < cells.length; j++) {
            const cellText = cells[j].textContent || cells[j].innerText;
            if (cellText.toLowerCase().indexOf(searchText) > -1) {
                found = true;
                break;
            }
        }
        
        row.style.display = found ? '' : 'none';
    }
}

// Initialize when document is ready
document.addEventListener('DOMContentLoaded', function() {
    // Add event listener to search input
    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
        searchInput.addEventListener('keyup', filterPayments);
    }
    
    // Other initialization code...
});
});