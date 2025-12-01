
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

    function connectWebSocket() {
        const socket = new WebSocket('ws://127.0.0.1:8765');

        socket.onopen = () => {
            console.log('WebSocket connection established');
            statusDiv.textContent = 'Connected';
            statusDiv.className = 'connected';
        };

        socket.onmessage = (event) => {
            console.log('Message from server ', event.data);
            const message = JSON.parse(event.data);

            if (message.type === 'post_detail') {
                updatePostDetails(message.data);
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
        if (data.engagement_history && data.engagement_history.length > 0) {
            // Create datasets with x-y coordinates for proper time-based spacing
            const commentsData = data.engagement_history.map(e => ({
                x: new Date(e._downloaded_at),
                y: e.comments || 0
            }));

            const reactionsData = data.engagement_history.map(e => ({
                x: new Date(e._downloaded_at),
                y: e.reactions || 0
            }));

            if (engagementChart) {
                engagementChart.destroy();
            }

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
        } else {
             if (engagementChart) {
                engagementChart.destroy();
                engagementChart = null;
            }
        }
    }

    connectWebSocket();
});
