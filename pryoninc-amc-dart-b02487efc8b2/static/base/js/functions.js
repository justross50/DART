function validateForm() {
    var inputVal = document.getElementById("name").value;
    if (inputVal.trim() === "") {
        alert("Please enter a name.");
        return false;
    }
    return true;
}
