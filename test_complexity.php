<?php
// Simple function - McCabe 1
function simple_add($a, $b) {
    return $a + $b;
}

// Moderate complexity - McCabe ~4
function validate_user($username, $password, $remember_me = false) {
    if (empty($username) || empty($password)) {
        return false;
    }
    if (strlen($password) < 8) {
        throw new Exception("Password too short");
    }
    if ($remember_me && !isset($_COOKIE['token'])) {
        setcookie('token', bin2hex(random_bytes(32)), time() + 86400 * 30);
    }
    return true;
}

// Complex function - McCabe ~8
function process_order($items, $user, $payment_method) {
    $total = 0;
    foreach ($items as $item) {
        if ($item['quantity'] > 0) {
            if (isset($item['discount']) && $item['discount'] > 0) {
                $price = $item['price'] * (1 - $item['discount'] / 100);
            } else {
                $price = $item['price'];
            }
            $total += $price * $item['quantity'];
        } elseif ($item['quantity'] < 0) {
            throw new InvalidArgumentException("Negative quantity");
        }
    }
    
    switch ($payment_method) {
        case 'credit':
            $fee = $total * 0.025;
            break;
        case 'paypal':
            $fee = $total * 0.035;
            break;
        case 'crypto':
            $fee = $total * 0.01;
            break;
        default:
            $fee = 0;
    }
    
    if ($user['vip'] && $total > 100) {
        $fee = 0;
    }
    
    if ($total > 1000 && !$user['verified']) {
        throw new Exception("Large orders require verification");
    }
    
    return $total + $fee;
}

class OrderProcessor {
    public function handle($order) {
        // McCabe ~3
        if (!$order || !$order->isValid()) {
            return null;
        }
        try {
            return $this->process($order);
        } catch (Exception $e) {
            error_log($e->getMessage());
            return false;
        }
    }
    
    private function process($order) {
        return $order->save() && $order->notify();
    }
}
