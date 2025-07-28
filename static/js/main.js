document.addEventListener('DOMContentLoaded', () => {
    try {
        console.log("DOM fully loaded, initializing app...");
        
        let pdfDoc = null;
        let currentPage = 1;
        let totalPages = 0;
        let selectedFile = null;
        
        // DOM elements - add error checking for each element
        const pdfViewer = document.getElementById('pdf-viewer');
        console.log("PDF Viewer element found:", !!pdfViewer);
        
        const prevPageBtn = document.getElementById('prev-page');
        const nextPageBtn = document.getElementById('next-page');
        const pageInfo = document.getElementById('page-info');
        const chatBox = document.getElementById('chat-box');
        const chatWelcomeMessage = document.getElementById('chat-welcome-message');
        const userInput = document.getElementById('user-input');
        const sendBtn = document.getElementById('send-btn');
        const fileListContainer = document.getElementById('file-list-container');
        const fileCount = document.getElementById('file-count');
        const chatStatus = document.getElementById('chat-status');
        const charCount = document.getElementById('char-count');
        const clearChatBtn = document.getElementById('clear-chat-btn');

        // Initialize chat box with fixed height to ensure scrollability
        if (chatBox) {
            chatBox.style.height = '90%';
            chatBox.style.maxHeight = '68vh';
            chatBox.style.overflowY = 'auto';
        }

        // Modal elements
        const uploadModal = document.getElementById('upload-modal');
        console.log("Upload modal element found:", !!uploadModal);
        
        const uploadForm = document.getElementById('upload-form');
        const pdfFileInput = document.getElementById('pdf-file');
        const cancelUpload = document.getElementById('cancel-upload');
        const uploadSubmit = document.getElementById('upload-submit');
        const loadingOverlay = document.getElementById('loading-overlay');

        // Floating action button
        const floatingUploadBtn = document.querySelector('.floating-upload-btn');
        console.log("Upload button found:", !!floatingUploadBtn);

        // Initialize showdown converter if available
        let converter;
        if (typeof showdown !== 'undefined') {
            converter = new showdown.Converter({
                tables: true,
                strikethrough: true,
                tasklists: true,
                simpleLineBreaks: true
            });
        } else {
            console.error("Showdown library not loaded!");
        }

        // Initialize
        if (userInput) userInput.disabled = true;
        if (sendBtn) sendBtn.disabled = true;
        if (chatStatus) chatStatus.textContent = 'Select a document';

        // Character count for input
        if (userInput && charCount) {
            userInput.addEventListener('input', () => {
                const count = userInput.value.length;
                charCount.textContent = `${count}/500`;
                if (count > 450) {
                    charCount.classList.add('text-red-500');
                    charCount.classList.remove('text-gray-500');
                } else {
                    charCount.classList.remove('text-red-500');
                    charCount.classList.add('text-gray-500');
                }
            });
        }

        // Upload modal handlers
        if (floatingUploadBtn) {
            console.log("Attaching click handler to upload button");
            floatingUploadBtn.addEventListener('click', function(e) {
                console.log("Upload button clicked");
                e.preventDefault();
                if (uploadModal) {
                    uploadModal.classList.remove('hidden');
                    uploadModal.classList.add('flex');
                    console.log("Upload modal displayed");
                } else {
                    console.error("Upload modal not found!");
                }
            });
        } else {
            console.error("Upload button not found in DOM!");
        }

        if (cancelUpload) {
            cancelUpload.addEventListener('click', function(e) {
                e.preventDefault();
                closeUploadModal();
            });
        }

        if (uploadModal) {
            uploadModal.addEventListener('click', (e) => {
                if (e.target === uploadModal) {
                    closeUploadModal();
                }
            });
        }

        // File upload handling
        if (uploadForm) {
            uploadForm.addEventListener('submit', (e) => {
                console.log("Upload form submitted");
                e.preventDefault();
                const file = pdfFileInput.files[0];
                if (!file || file.type !== 'application/pdf') {
                    alert('Please select a PDF file.');
                    return;
                }

                if (file.size > 10 * 1024 * 1024) { // 10MB limit
                    alert('File size must be less than 10MB.');
                    return;
                }

                showUploadLoading();
                
                const formData = new FormData();
                formData.append('file', file);
                
                fetch('/upload', {
                    method: 'POST',
                    body: formData
                })
                .then(response => response.json())
                .then(data => {
                    if (data.error) {
                        alert(data.error);
                        resetUploadButton();
                    } else {
                        closeUploadModal();
                        showNotification('PDF uploaded successfully!', 'success');
                        addFileToList(data.filename);
                        resetUploadButton();
                    }
                })
                .catch(error => {
                    console.error('Upload error:', error);
                    alert('Upload failed. Please try again.');
                    resetUploadButton();
                });
            });
        }

        // File selection handling
        if (fileListContainer) {
            fileListContainer.addEventListener('click', (e) => {
                console.log("File list container clicked", e.target);
                const fileBtn = e.target.closest('.file-btn');
                const deleteBtn = e.target.closest('.delete-btn');

                if (deleteBtn) {
                    const listItem = deleteBtn.closest('li');
                    const filename = listItem.dataset.filename;
                    if (confirm(`Are you sure you want to delete "${filename}"? This action cannot be undone.`)) {
                        deleteDocument(filename, listItem);
                    }
                    return; // Stop further processing
                }

                if (fileBtn) {
                    console.log("File button clicked:", fileBtn.dataset.filename);
                    // Remove active state from other buttons
                    document.querySelectorAll('.file-btn').forEach(btn => {
                        btn.classList.remove('ring-2', 'ring-blue-500');
                    });
                    
                    // Add active state to clicked button
                    fileBtn.classList.add('ring-2', 'ring-blue-500');
                    
                    selectedFile = fileBtn.getAttribute('data-filename');
                    loadPdf(`/uploads/${selectedFile}`);
                    loadHistory(selectedFile);
                    enableChat(true);
                    updateChatStatus('Connected to document');
                }
            });
        }

        // Page navigation
        if (prevPageBtn) {
            prevPageBtn.addEventListener('click', () => {
                if (currentPage > 1) {
                    currentPage--;
                    renderPage(currentPage);
                    updatePageControls();
                }
            });
        }

        if (nextPageBtn) {
            nextPageBtn.addEventListener('click', () => {
                if (currentPage < totalPages) {
                    currentPage++;
                    renderPage(currentPage);
                    updatePageControls();
                }
            });
        }

        // Chat functionality
        const inputContainer = document.getElementById('input-container');
        
        // Prevent form submission
        if (inputContainer) {
            inputContainer.addEventListener('submit', (e) => {
                e.preventDefault();
                askQuestion();
            });
        }

        if (sendBtn) {
            sendBtn.addEventListener('click', (e) => {
                e.preventDefault();
                askQuestion();
            });
        }

        if (userInput) {
            userInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    askQuestion();
                }
            });
            // Remove auto-resize to keep input fixed height
        }

        if (clearChatBtn) {
            clearChatBtn.addEventListener('click', () => {
                if (selectedFile && confirm('Are you sure you want to clear the chat history for this document?')) {
                    clearChatHistory(selectedFile);
                }
            });
        }

        // Feedback handling - use event delegation on chatBox
        if (chatBox) {
            chatBox.addEventListener('click', (e) => {
                const feedbackBtn = e.target.closest('.feedback-btn');
                if (feedbackBtn) {
                    const feedbackContainer = feedbackBtn.closest('.feedback-container');
                    const feedback = feedbackBtn.dataset.feedback;
                    const question = decodeURIComponent(feedbackContainer.dataset.question || '');
                    const answer = decodeURIComponent(feedbackContainer.dataset.answer || '');
                    
                    console.log('Feedback button clicked:', feedback, 'Question:', question, 'Answer length:', answer.length);
                    
                    if (feedback === 'like') {
                        sendFeedback(question, answer, 'like', '', feedbackContainer);
                    } else if (feedback === 'dislike') {
                        showFeedbackModal(question, answer, feedbackContainer);
                    }
                }
            });
        }

        function showFeedbackModal(question, answer, feedbackContainer) {
            const modal = document.createElement('div');
            modal.className = 'fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4';
            modal.innerHTML = `
                <div class="bg-white rounded-2xl shadow-2xl max-w-md w-full p-6 animate-slide-up">
                    <div class="text-center mb-6">
                        <div class="w-16 h-16 bg-gradient-to-br from-red-500 to-pink-600 rounded-2xl flex items-center justify-center mx-auto mb-4">
                            <svg class="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 14H5.236a2 2 0 01-1.789-2.894l3.5-7A2 2 0 018.736 3h4.018c.163 0 .326.02.485.06L17 4m-7 10v2a2 2 0 002 2h.095c.5 0 .905-.405.905-.905 0-.714.211-1.412.608-2.006L15 17V4m-3 10h.5a2 2 0 002-2V6a2 2 0 00-2-2h-.5m-3 10h-.5a2 2 0 01-2-2V6a2 2 0 012-2h.5"/>
                            </svg>
                        </div>
                        <h3 class="text-xl font-semibold text-gray-900 mb-2">Feedback on Answer</h3>
                        <p class="text-sm text-gray-600">Help us improve by telling us what went wrong</p>
                    </div>
                    
                    <form class="space-y-4">
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-2">What needs improvement?</label>
                            <textarea id="feedback-text" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent resize-none" rows="4" placeholder="Please describe what was wrong or how it could be improved..."></textarea>
                        </div>
                        
                        <div class="flex space-x-3">
                            <button type="button" class="cancel-feedback flex-1 px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg transition-colors">
                                Cancel
                            </button>
                            <button type="submit" class="submit-feedback flex-1 px-4 py-2 bg-gradient-to-r from-red-600 to-pink-600 hover:from-red-700 hover:to-pink-700 text-white rounded-lg transition-all duration-200">
                                Submit Feedback
                            </button>
                        </div>
                    </form>
                </div>
            `;
            
            document.body.appendChild(modal);
            
            // Focus on textarea
            const textarea = modal.querySelector('#feedback-text');
            textarea.focus();
            
            // Handle modal close
            const cancelBtn = modal.querySelector('.cancel-feedback');
            cancelBtn.addEventListener('click', () => {
                document.body.removeChild(modal);
            });
            
            // Handle click outside modal
            modal.addEventListener('click', (e) => {
                if (e.target === modal) {
                    document.body.removeChild(modal);
                }
            });
            
            // Handle form submission
            const form = modal.querySelector('form');
            form.addEventListener('submit', (e) => {
                e.preventDefault();
                const feedbackText = textarea.value.trim();
                if (feedbackText) {
                    sendFeedback(question, answer, 'dislike', feedbackText, feedbackContainer);
                    document.body.removeChild(modal);
                } else {
                    textarea.focus();
                    textarea.classList.add('border-red-500');
                    setTimeout(() => textarea.classList.remove('border-red-500'), 2000);
                }
            });
        }

        function sendFeedback(question, answer, feedbackType, additionalInfo, feedbackContainer) {
            if (!selectedFile) {
                showNotification('No document selected', 'error');
                return;
            }
            
            console.log('Sending feedback:', { 
                question: question, 
                answer: answer.substring(0, 100) + '...', 
                feedbackType: feedbackType, 
                additionalInfo: additionalInfo,
                selectedFile: selectedFile 
            });
            
            // Validate required fields
            if (!question || !answer || !feedbackType) {
                console.error('Missing required fields:', { question: !!question, answer: !!answer, feedbackType: !!feedbackType });
                showNotification('Missing required information for feedback', 'error');
                return;
            }
            
            fetch('/feedback', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    filename: selectedFile,
                    question: question,
                    answer: answer,
                    feedback_type: feedbackType,
                    additional_info: additionalInfo
                })
            })
            .then(response => response.json())
            .then(data => {
                console.log('Feedback response:', data);
                if (data.message) {
                    showNotification('Feedback submitted successfully!', 'success');
                    
                    // Update the feedback container to show submitted state
                    if (feedbackType === 'like') {
                        feedbackContainer.innerHTML = `
                            <div class="feedback-display mt-3 text-xs text-green-600 flex items-center">
                                <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 10h4.764a2 2 0 011.789 2.894l-3.5 7A2 2 0 0115.263 21h-4.017c-.163 0-.326-.02-.485-.06L7 20m7-10V5a2 2 0 00-2-2h-.095c-.5 0-.905.405-.905.905 0 .714-.211 1.412-.608 2.006L9 7v13m-3-10h-.5a2 2 0 00-2 2v6a2 2 0 002 2h.5m3-10h.5a2 2 0 012 2v6a2 2 0 01-2 2h-.5"/>
                                </svg>
                                Thank you! You found this helpful.
                            </div>
                        `;
                    } else {
                        feedbackContainer.innerHTML = `
                            <div class="feedback-display mt-3 text-xs text-red-600 flex items-center">
                                <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 14H5.236a2 2 0 01-1.789-2.894l3.5-7A2 2 0 018.736 3h4.018c.163 0 .326.02.485.06L17 4m-7 10v2a2 2 0 002 2h.095c.5 0 .905-.405.905-.905 0-.714.211-1.412.608-2.006L15 17V4m-3 10h.5a2 2 0 002-2V6a2 2 0 00-2-2h-.5m-3 10h-.5a2 2 0 01-2-2V6a2 2 0 012-2h.5"/>
                                </svg>
                                Thank you for your feedback! We'll improve this.
                            </div>
                        `;
                    }
                } else {
                    showNotification(data.error || 'Failed to submit feedback.', 'error');
                }
            })
            .catch(error => {
                console.error('Feedback error:', error);
                showNotification('An error occurred while submitting feedback.', 'error');
            });
        }

        // Functions
        function closeUploadModal() {
            console.log("Closing upload modal");
            if (uploadModal) {
                uploadModal.classList.add('hidden');
                uploadModal.classList.remove('flex');
                if (uploadForm) uploadForm.reset();
                resetUploadButton();
            }
        }

        function resetUploadButton() {
            uploadSubmit.disabled = false;
            const uploadText = uploadSubmit.querySelector('.upload-text');
            const uploadLoading = uploadSubmit.querySelector('.upload-loading');
            if (uploadText) uploadText.classList.remove('hidden');
            if (uploadLoading) uploadLoading.classList.add('hidden');
        }

        function showUploadLoading() {
            uploadSubmit.disabled = true;
            const uploadText = uploadSubmit.querySelector('.upload-text');
            const uploadLoading = uploadSubmit.querySelector('.upload-loading');
            if (uploadText) uploadText.classList.add('hidden');
            if (uploadLoading) uploadLoading.classList.remove('hidden');
        }

        function showLoadingOverlay() {
            loadingOverlay.classList.remove('hidden');
            loadingOverlay.classList.add('flex');
        }

        function hideLoadingOverlay() {
            loadingOverlay.classList.add('hidden');
            loadingOverlay.classList.remove('flex');
        }

        function loadPdf(url) {
            showLoadingOverlay();
            pdfjsLib.getDocument(url).promise.then(pdf => {
                pdfDoc = pdf;
                totalPages = pdf.numPages;
                currentPage = 1;
                renderPage(1);
                updatePageControls();
                hideLoadingOverlay();
            }).catch(error => {
                console.error('Error loading PDF:', error);
                hideLoadingOverlay();
                showNotification('Failed to load PDF', 'error');
            });
        }

        function renderPage(pageNum) {
            if (!pdfDoc) return;
            
            pdfDoc.getPage(pageNum).then(page => {
                // Get the container dimensions
                const containerWidth = pdfViewer.clientWidth - 48; // Account for padding
                const containerHeight = pdfViewer.clientHeight - 48; // Account for padding
                
                // Get the page's natural viewport at scale 1
                const viewport = page.getViewport({ scale: 1 });
                
                // Calculate scale to fit within container while maintaining aspect ratio
                const scaleX = containerWidth / viewport.width;
                const scaleY = containerHeight / viewport.height;
                const scale = Math.min(scaleX, scaleY, 1.0); // Don't scale larger than original
                
                // Get the final viewport with calculated scale
                const scaledViewport = page.getViewport({ scale });
                
                // Clear previous content
                pdfViewer.innerHTML = '';
                
                const canvas = document.createElement('canvas');
                canvas.className = 'pdf-canvas max-w-full max-h-full border border-gray-200 rounded-lg shadow-sm mx-auto';
                const context = canvas.getContext('2d');
                canvas.height = scaledViewport.height;
                canvas.width = scaledViewport.width;
                
                // Center the canvas in the container
                canvas.style.display = 'block';
                canvas.style.margin = 'auto';
                
                pdfViewer.appendChild(canvas);
                
                const renderContext = {
                    canvasContext: context,
                    viewport: scaledViewport
                };
                
                page.render(renderContext).promise.then(() => {
                    console.log('Page rendered successfully at scale:', scale);
                });
            }).catch(error => {
                console.error('Error rendering page:', error);
            });
        }

        function updatePageControls() {
            if (pageInfo) {
                pageInfo.textContent = totalPages > 0 ? `${currentPage} / ${totalPages}` : '';
            }
            
            if (prevPageBtn) {
                prevPageBtn.disabled = currentPage <= 1;
            }
            
            if (nextPageBtn) {
                nextPageBtn.disabled = currentPage >= totalPages;
            }
        }

        function updateChatStatus(status) {
            if (chatStatus) {
                chatStatus.textContent = status;
            }
        }

        function enableChat(enabled) {
            console.log("Setting chat enabled:", enabled);
            if (userInput) userInput.disabled = !enabled;
            if (sendBtn) sendBtn.disabled = !enabled;
            updateChatStatus(enabled ? 'Ready' : 'Select a document');
        }

        function askQuestion() {
            const question = userInput.value.trim();
            if (!question || !selectedFile) return;
            
            appendMessage('user', question);
            userInput.value = '';
            updateChatStatus('Thinking...');
            
            fetch('/ask', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ question: question, filename: selectedFile })
            })
            .then(response => response.json())
            .then(data => {
                updateChatStatus('Ready');
                if (data.error) {
                    appendMessage('assistant', data.error);
                } else {
                    // Pass the original question to appendMessage for feedback purposes
                    appendMessage('assistant', data.answer, data.message_id, data.source_page, null, question);
                    if (data.source_page && pdfDoc) {
                        currentPage = data.source_page;
                        renderPage(currentPage);
                        updatePageControls();
                        showNotification(`Navigated to page ${currentPage} for context`, 'info');
                    }
                }
            })
            .catch(error => {
                console.error('Chat error:', error);
                updateChatStatus('Error');
                appendMessage('assistant', 'Sorry, I encountered an error. Please try again.');
            });
        }

        function appendMessage(role, content, messageId = null, sourcePage = null, feedback = null, question = null) {
            if (chatWelcomeMessage) {
                chatWelcomeMessage.style.display = 'none';
            }
            const messageElement = document.createElement('div');
            messageElement.classList.add('flex', role === 'user' ? 'justify-end' : 'justify-start', 'animate-fade-in');
            
            let contentHtml;
            
            if (role === 'user') {
                contentHtml = `
                    <div class="max-w-[80%]">
                        <div class="bg-gradient-to-r from-purple-600 to-pink-600 text-white p-4 rounded-xl rounded-br-none shadow-md">
                            <p class="text-sm leading-relaxed">${content}</p>
                        </div>
                    </div>
                `;
            } else { // Bot message
                const htmlContent = converter.makeHtml(content);
                const sourceInfo = sourcePage ? `<p class="text-xs text-gray-500 mt-2">📖 Source: Page ${sourcePage}</p>` : '';
                
                // Create feedback buttons for AI responses
                let feedbackHtml = `
                    <div class="feedback-container mt-3 flex items-center space-x-2" data-question="${encodeURIComponent(question || '')}" data-answer="${encodeURIComponent(content)}">
                        <span class="text-xs text-gray-500">Was this helpful?</span>
                        <button class="feedback-btn like-btn p-2 rounded-full hover:bg-green-100 transition-colors text-gray-400 hover:text-green-600" data-feedback="like" title="Helpful">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 10h4.764a2 2 0 011.789 2.894l-3.5 7A2 2 0 0115.263 21h-4.017c-.163 0-.326-.02-.485-.06L7 20m7-10V5a2 2 0 00-2-2h-.095c-.5 0-.905.405-.905.905 0 .714-.211 1.412-.608 2.006L9 7v13m-3-10h-.5a2 2 0 00-2 2v6a2 2 0 002 2h.5m3-10h.5a2 2 0 012 2v6a2 2 0 01-2 2h-.5"/>
                            </svg>
                        </button>
                        <button class="feedback-btn dislike-btn p-2 rounded-full hover:bg-red-100 transition-colors text-gray-400 hover:text-red-600" data-feedback="dislike" title="Not Helpful">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 14H5.236a2 2 0 01-1.789-2.894l3.5-7A2 2 0 018.736 3h4.018c.163 0 .326.02.485.06L17 4m-7 10v2a2 2 0 002 2h.095c.5 0 .905-.405.905-.905 0-.714.211-1.412.608-2.006L15 17V4m-3 10h.5a2 2 0 002-2V6a2 2 0 00-2-2h-.5m-3 10h-.5a2 2 0 01-2-2V6a2 2 0 012-2h.5"/>
                            </svg>
                        </button>
                    </div>
                `;

                contentHtml = `
                    <div class="flex items-start space-x-3 max-w-[80%]">
                        <div class="flex-shrink-0 w-8 h-8 bg-gradient-to-br from-purple-500 to-pink-600 rounded-lg flex items-center justify-center shadow-sm">
                            <svg class="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"/></svg>
                        </div>
                        <div class="bg-white p-4 rounded-xl rounded-tl-none shadow-md">
                            <div class="markdown-body">${htmlContent}</div>
                            ${sourceInfo}
                            ${feedbackHtml}
                        </div>
                    </div>
                `;
            }
            
            messageElement.innerHTML = contentHtml;
            chatBox.appendChild(messageElement);
            
            // Ensure smooth scrolling to the bottom with a slight delay to account for rendering
            setTimeout(() => {
                chatBox.scrollTop = chatBox.scrollHeight;
            }, 100);
        }

        function loadHistory(filename) {
            chatBox.innerHTML = '';
            if (chatWelcomeMessage) {
                chatWelcomeMessage.style.display = 'block';
                chatWelcomeMessage.querySelector('p:last-child').textContent = `Ask me anything about "${filename}"`;
            }
            
            fetch(`/history?filename=${encodeURIComponent(filename)}`)
                .then(response => response.json())
                .then(data => {
                    if (data.history && data.history.length > 0) {
                        chatBox.innerHTML = '';
                        let lastUserQuestion = '';
                        data.history.forEach(msg => {
                            if (msg.role === 'user') {
                                lastUserQuestion = msg.content;
                                appendMessage(msg.role, msg.content, msg.id, null, msg.feedback);
                            } else {
                                // Pass the last user question for feedback purposes
                                appendMessage(msg.role, msg.content, msg.id, null, msg.feedback, lastUserQuestion);
                            }
                        });
                    }
                })
                .catch(error => {
                    console.error('History load error:', error);
                });
        }

        function clearChatHistory(filename) {
            showLoadingOverlay();
            fetch('/clear_chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filename: filename })
            })
            .then(response => response.json())
            .then(data => {
                hideLoadingOverlay();
                if (data.error) {
                    showNotification(data.error, 'error');
                } else {
                    showNotification(data.success, 'success');
                    loadHistory(filename); // Reload to show the cleared state
                    if (chatWelcomeMessage) {
                        chatWelcomeMessage.style.display = 'block';
                    }
                }
            })
            .catch(error => {
                hideLoadingOverlay();
                console.error('Clear chat error:', error);
                showNotification('Failed to clear chat history.', 'error');
            });
        }

        function showNotification(message, type = 'info') {
            const notification = document.createElement('div');
            notification.className = `
                fixed top-4 right-4 z-50 p-4 rounded-lg shadow-lg max-w-sm animate-slide-up
                ${type === 'success' ? 'bg-green-100 border border-green-200 text-green-800' : 
                  type === 'error' ? 'bg-red-100 border border-red-200 text-red-800' : 
                  'bg-blue-100 border border-blue-200 text-blue-800'}
            `;
            
            notification.innerHTML = `
                <div class="flex items-center space-x-2">
                    <div class="flex-shrink-0">
                        ${type === 'success' ? 
                            '<svg class="w-5 h-5 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>' :
                          type === 'error' ?
                            '<svg class="w-5 h-5 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>' :
                            '<svg class="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>'
                        }
                    </div>
                    <p class="text-sm font-medium">${message}</p>
                </div>
            `;
            
            document.body.appendChild(notification);
            
            setTimeout(() => {
                notification.style.transform = 'translateX(100%)';
                notification.style.opacity = '0';
                setTimeout(() => {
                    if (document.body.contains(notification)) {
                        document.body.removeChild(notification);
                    }
                }, 300);
            }, 3000);
        }

        function addFileToList(filename) {
            // Check if file already exists in the list
            const existingFileBtn = document.querySelector(`[data-filename="${filename}"]`);
            if (existingFileBtn) {
                return; // File already exists, don't add duplicate
            }

            // Get the file list container
            const fileListElement = document.getElementById('file-list');
            const noDocumentsMessage = fileListContainer.querySelector('.text-center');
            
            // Remove "no documents" message if it exists
            if (noDocumentsMessage && !fileListElement) {
                fileListContainer.innerHTML = '<ul id="file-list" class="space-y-3"></ul>';
            }
            
            // Get or create the file list
            const fileList = document.getElementById('file-list') || (() => {
                const ul = document.createElement('ul');
                ul.id = 'file-list';
                ul.className = 'space-y-3';
                fileListContainer.appendChild(ul);
                return ul;
            })();

            // Create new file list item
            const listItem = document.createElement('li');
            listItem.className = 'group animate-slide-up';
            listItem.innerHTML = `
                <button class="file-btn w-full text-left p-4 rounded-xl bg-gradient-to-r from-gray-50 to-blue-50 hover:from-blue-50 hover:to-indigo-50 border border-gray-200 hover:border-blue-300 transition-all duration-300 transform hover:scale-[1.02] hover:shadow-lg" data-filename="${filename}">
                    <div class="flex items-center space-x-3">
                        <div class="flex-shrink-0 w-10 h-10 bg-gradient-to-br from-red-400 to-red-600 rounded-lg flex items-center justify-center shadow-sm group-hover:shadow-md transition-shadow">
                            <svg class="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z"/>
                            </svg>
                        </div>
                        <div class="flex-1 min-w-0">
                            <p class="text-sm font-medium text-gray-900 truncate group-hover:text-blue-700 transition-colors">${filename}</p>
                            <p class="text-xs text-gray-500">PDF Document</p>
                        </div>
                        <div class="flex-shrink-0">
                            <div class="w-2 h-2 bg-green-400 rounded-full opacity-0 group-hover:opacity-100 transition-opacity"></div>
                        </div>
                    </div>
                </button>
            `;

            // Add to the beginning of the list
            fileList.insertBefore(listItem, fileList.firstChild);

            // Update file count
            if (fileCount) {
                const currentCount = parseInt(fileCount.textContent) || 0;
                fileCount.textContent = currentCount + 1;
            }

            // Auto-select the newly uploaded file
            setTimeout(() => {
                const newFileBtn = listItem.querySelector('.file-btn');
                if (newFileBtn) {
                    // Remove active state from other buttons
                    document.querySelectorAll('.file-btn').forEach(btn => {
                        btn.classList.remove('ring-2', 'ring-blue-500');
                    });
                    
                    // Add active state to new button
                    newFileBtn.classList.add('ring-2', 'ring-blue-500');
                    
                    // Load the PDF and enable chat
                    selectedFile = filename;
                    loadPdf(`/uploads/${filename}`);
                    loadHistory(filename);
                    enableChat(true);
                    updateChatStatus('Connected to document');
                }
            }, 100);
        }

        function deleteDocument(filename, listItemElement) {
            showLoadingOverlay();
            fetch('/delete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filename: filename })
            })
            .then(response => response.json())
            .then(data => {
                hideLoadingOverlay();
                if (data.error) {
                    showNotification(data.error, 'error');
                } else {
                    showNotification(data.success, 'success');
                    listItemElement.remove();
                    
                    // Update file count
                    if (fileCount) {
                        const currentCount = parseInt(fileCount.textContent) || 0;
                        fileCount.textContent = Math.max(0, currentCount - 1);
                    }

                    // If the deleted file was the selected one, reset the view
                    if (selectedFile === filename) {
                        resetUI();
                    }
                }
            })
            .catch(error => {
                hideLoadingOverlay();
                console.error('Delete error:', error);
                showNotification('Failed to delete document.', 'error');
            });
        }

        function resetUI() {
            selectedFile = null;
            pdfDoc = null;
            pdfViewer.innerHTML = `
                <div class="text-center">
                    <div class="w-20 h-20 bg-white rounded-2xl shadow-lg flex items-center justify-center mx-auto mb-6 animate-bounce-gentle">
                        <svg class="w-10 h-10 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
                        </svg>
                    </div>
                    <h4 class="text-lg font-semibold text-gray-700 mb-2">Ready for your document</h4>
                    <p class="text-sm text-gray-500 mb-4">Select a PDF from your library to start viewing</p>
                    <div class="flex items-center justify-center space-x-2 text-xs text-gray-400">
                        <div class="w-2 h-2 bg-blue-400 rounded-full animate-pulse"></div>
                        <span>Waiting for selection...</span>
                    </div>
                </div>
            `;
            chatBox.innerHTML = '';
            if (chatWelcomeMessage) {
                chatWelcomeMessage.style.display = 'block';
            }
            enableChat(false);
            updatePageControls();
        }
    } catch (error) {
        console.error("Critical error in initialization:", error);
        alert("There was an error initializing the application. Please check the console for details.");
    }
});

// Test if the script is loaded
console.log("PDF Bot script loaded");
