// static/js/room_actions.js
"use strict";

document.addEventListener('DOMContentLoaded', () => {
    console.log("Initializing room_actions.js...");

    // Use event delegation for archive buttons
    document.body.addEventListener('click', async (event) => {
        const archiveButton = event.target.closest('button[data-action="archive-room"]');
        if (!archiveButton) {
            return; // Click wasn't on an archive button
        }

        const roomName = archiveButton.dataset.roomName || 'this room';
        const archiveUrl = archiveButton.dataset.url;
        const roomListItem = archiveButton.closest('.room-list-item'); // Find the parent item to remove

        if (!archiveUrl) {
            console.error("Archive button missing data-url attribute.");
            if (window.showNotification) showNotification("Action URL not found.", "error");
            return;
        }

        // Confirmation (Using SweetAlert2 if available, otherwise confirm)
        let confirmed = false;
        const confirmationText = `Are you sure you want to archive room "${escapeHtml(roomName)}"? You can unarchive it later via the admin interface.`; // Basic English text
        if (typeof Swal !== 'undefined') {
            const result = await Swal.fire({
                title: 'Archive Room?', // Hardcoded English
                text: confirmationText,
                icon: 'warning',
                showCancelButton: true,
                confirmButtonColor: '#e53e3e', // Red
                cancelButtonColor: '#718096', // Gray
                confirmButtonText: 'Yes, archive it!', // Hardcoded English
                cancelButtonText: 'Cancel' // Hardcoded English
            });
            confirmed = result.isConfirmed;
        } else {
            confirmed = confirm(confirmationText);
        }

        if (confirmed) {
            console.log(`Attempting to archive room via ${archiveUrl}`);
             // Use authenticatedFetch from app_utils.js (assumes it handles CSRF)
             if (!window.authenticatedFetch) {
                console.error("authenticatedFetch utility is not available.");
                if(window.showNotification) showNotification("Utility function missing.", "error");
                return;
             }

            try {
                 // Send POST request to archive
                 const response = await window.authenticatedFetch(archiveUrl, { method: 'POST' });

                 if (response.ok) {
                     const responseData = await response.json().catch(() => ({})); // Handle potential empty response
                     if (responseData.success !== false) {
                         console.log(`Room "${roomName}" archived successfully.`);
                         if (window.showNotification) showNotification(responseData.message || `Room "${escapeHtml(roomName)}" archived.`, 'success');
                         // Remove the room item from the UI
                         if (roomListItem) {
                             roomListItem.style.transition = 'opacity 0.3s ease-out';
                             roomListItem.style.opacity = '0';
                             setTimeout(() => roomListItem.remove(), 300);
                         }
                          // If archiving from the room page itself, redirect
                          if (window.roomSlug && archiveUrl.includes(window.roomSlug)) {
                               window.location.href = "{% url 'room:rooms' %}"; // Redirect to room list
                          }
                     } else {
                         throw new Error(responseData.error || 'Server indicated failure.');
                     }
                 } else {
                      throw new Error(`Server error: ${response.status}`);
                 }
            } catch (error) {
                 console.error(`Failed to archive room "${roomName}":`, error);
                 // Notification should be shown by authenticatedFetch or here
                 if (window.showNotification && !error.handled) showNotification(`Error archiving: ${error.message}`, 'error');
            }
        }
    });

    console.log("room_actions.js initialized.");
});