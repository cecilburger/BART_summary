window.addEventListener("load", function() {
    document.getElementById("loading-screen").style.display = "none"; // Hide loading screen on page load
});

document.getElementById('searchButton')?.addEventListener('click', function(event) {
    const query = document.getElementById('query').value;
    if (query) {
        document.getElementById("loading-screen").style.display = "flex"; // Show loading screen on search button click
    } else {
        event.preventDefault(); // Prevent form submission if no query
        window.location.href = 'error.html'; // Redirect to error page if no query
    }
});
