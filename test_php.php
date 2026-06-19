<?php
// Test file for php_checker.py — contains intentional issues
$password = "supersecret123";  // HIGH: hardcoded password
$db_user = "admin";            // HIGH: hardcoded DB creds
$api_key = "sk-1234567890abcdef";  // HIGH: hardcoded secret

$id = $_GET['id'];
$name = $_GET['name'];

// HIGH: SQL injection
$query = "SELECT * FROM users WHERE id = " . $id;
$result = mysql_query($query);  // deprecated mysql_*

// HIGH: XSS
echo $_GET['message'];

// HIGH: file inclusion
include $_GET['page'] . ".php";

// HIGH: command injection
system("ping " . $_GET['host']);

// HIGH: eval
eval("echo 'Hello " . $name . "';");

// MEDIUM: md5 for password
$hashed = md5($password);

// MEDIUM: extract on globals
extract($_POST);

// MEDIUM: no CSRF token
echo '<form method="post" action="/login"><input name="user"></form>';

// QUALITY: short open tag (if this file started with <?)
// QUALITY: @ suppression
@mysql_connect("localhost", "root", "");

// QUALITY: debug output
var_dump($result);
print_r($_SERVER);
die("debug stop");

// QUALITY: nested ternary
$out = $a ? $b ? $c : $d : $e;

// TODO: fix this later
// FIXME: broken auth check
?>
