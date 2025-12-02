
document.addEventListener('DOMContentLoaded', () => {
    const statusDiv = document.getElementById('status');
    const welcomeDiv = document.getElementById('welcome');
    const postDetailsDiv = document.getElementById('post-details');
    const postAuthor = document.getElementById('post-author');
    const postUrl = document.getElementById('post-url');
    const postText = document.getElementById('post-text');
    const postMedia = document.getElementById('post-media');
    const chartCanvas = document.getElementById('engagement-chart');

    let engagementChart = null;

    async function loadConfig() {
        try {
            const response = await fetch('ws_config.json');
            const config = await response.json();
            return config.port || 8765;
        } catch {
            return 8765;  // Fallback to default
        }
    }

    async function connectWebSocket() {
        const port = await loadConfig();
        const socket = new WebSocket(`ws://127.0.0.1:${port}`);

        socket.onopen = () => {
            console.log('WebSocket connection established');
            statusDiv.textContent = 'Connected';
            statusDiv.className = 'connected';
        };

        socket.onmessage = (event) => {
            console.log('[WebSocket] Raw message received, length:', event.data.length);
            const message = JSON.parse(event.data);
            console.log('[WebSocket] Parsed message:', message);
            console.log('[WebSocket] Message type:', message.type);

            if (message.type === 'post_detail') {
                console.log('[WebSocket] Post detail message detected, calling updatePostDetails...');
                updatePostDetails(message.data);
            } else {
                console.log('[WebSocket] Unknown message type:', message.type);
            }
        };

        socket.onclose = () => {
            console.log('WebSocket connection closed');
            statusDiv.textContent = 'Disconnected';
            statusDiv.className = 'disconnected';
            // Try to reconnect after 3 seconds
            setTimeout(connectWebSocket, 3000);
        };

        socket.onerror = (error) => {
            console.error('WebSocket error:', error);
            socket.close();
        };
    }

    function updatePostDetails(data) {
        console.log('[updatePostDetails] Received data:', data);

        welcomeDiv.classList.add('hidden');
        postDetailsDiv.classList.remove('hidden');

        const author = data.author || {};
        let name = author.name;
        if (!name) {
            name = `${author.first_name || ''} ${author.last_name || ''}`.trim() || 'N/A';
        }
        postAuthor.textContent = `${name} (@${author.username || 'N/A'})`;
        postUrl.href = data.url || '#';
        postText.textContent = data.text || 'No text available.';

        // Media
        postMedia.innerHTML = '';
        const media = data.media;
        if (media) {
            if (media.type === 'image' && media.url) {
                const img = document.createElement('img');
                img.src = media.url;
                postMedia.appendChild(img);
            } else if (media.type === 'images') {
                media.images.forEach(image => {
                    if(image.url) {
                        const img = document.createElement('img');
                        img.src = image.url;
                        postMedia.appendChild(img);
                    }
                });
            } else if (media.type === 'video' && media.url) {
                const video = document.createElement('video');
                video.src = media.url;
                video.controls = true;
                postMedia.appendChild(video);
            }
        }

        // Engagement Chart
        console.log('[updatePostDetails] Checking engagement_history...');
        console.log('  - engagement_history exists?', !!data.engagement_history);
        console.log('  - engagement_history length:', data.engagement_history ? data.engagement_history.length : 'N/A');
        console.log('  - engagement_history data:', data.engagement_history);

        if (data.engagement_history && data.engagement_history.length > 0) {
            console.log('[updatePostDetails] Processing engagement history for chart...');
            // Create datasets with x-y coordinates for proper time-based spacing
            const commentsData = data.engagement_history.map(e => ({
                x: new Date(e._downloaded_at),
                y: e.comments || 0
            }));

            const reactionsData = data.engagement_history.map(e => ({
                x: new Date(e._downloaded_at),
                y: e.reactions || 0
            }));

            console.log('[updatePostDetails] Prepared chart data:');
            console.log('  - Comments data points:', commentsData.length);
            console.log('  - Comments data:', commentsData);
            console.log('  - Reactions data points:', reactionsData.length);
            console.log('  - Reactions data:', reactionsData);

            if (engagementChart) {
                console.log('[updatePostDetails] Destroying existing chart...');
                engagementChart.destroy();
            }

            console.log('[updatePostDetails] Creating new chart...');
            engagementChart = new Chart(chartCanvas, {
                type: 'line',
                data: {
                    datasets: [
                        {
                            label: 'Reactions',
                            data: reactionsData,
                            borderColor: 'rgba(24, 119, 242, 1)',
                            backgroundColor: 'rgba(24, 119, 242, 0.2)',
                            fill: true,
                            tension: 0.1
                        },
                        {
                            label: 'Comments',
                            data: commentsData,
                            borderColor: 'rgba(76, 175, 80, 1)',
                            backgroundColor: 'rgba(76, 175, 80, 0.2)',
                            fill: true,
                            tension: 0.1
                        }
                    ]
                },
                options: {
                    responsive: true,
                    scales: {
                        x: {
                            type: 'time',
                            time: {
                                unit: 'day',
                                displayFormats: {
                                    day: 'MMM d',
                                    hour: 'MMM d HH:mm'
                                },
                                tooltipFormat: 'MMM d, yyyy HH:mm'
                            },
                            title: {
                                display: true,
                                text: 'Date'
                            },
                            ticks: {
                                source: 'auto',
                                autoSkip: true,
                                maxRotation: 45,
                                minRotation: 0
                            }
                        },
                        y: {
                            title: {
                                display: true,
                                text: 'Count'
                            },
                            beginAtZero: true
                        }
                    },
                    plugins: {
                        tooltip: {
                            mode: 'index',
                            intersect: false
                        },
                        legend: {
                            display: true,
                            position: 'top'
                        }
                    },
                    interaction: {
                        mode: 'nearest',
                        axis: 'x',
                        intersect: false
                    }
                }
            });
            console.log('[updatePostDetails] Chart created successfully!');
        } else {
            console.log('[updatePostDetails] No engagement history data - skipping chart');
            if (engagementChart) {
                console.log('[updatePostDetails] Destroying existing chart (no data)...');
                engagementChart.destroy();
                engagementChart = null;
            }
        }
        console.log('[updatePostDetails] Finished updating post details');
    }

    connectWebSocket();
});
