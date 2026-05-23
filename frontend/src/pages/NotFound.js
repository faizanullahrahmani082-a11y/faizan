import React from 'react';
import { Link } from 'react-router-dom';
import { Button } from '../components/ui/button';
import { HeartPulse } from 'lucide-react';

const NotFound = () => (
  <div className="min-h-screen bg-gradient-to-br from-background via-primary/5 to-background flex flex-col items-center justify-center p-4 text-center">
    <HeartPulse className="w-16 h-16 text-primary mb-4 opacity-60" />
    <h1 className="text-6xl font-bold text-primary mb-2">404</h1>
    <p className="text-xl font-medium mb-1">Page Not Found</p>
    <p className="text-muted-foreground mb-8 max-w-xs">
      The page you're looking for doesn't exist or has been moved.
    </p>
    <Link to="/dashboard">
      <Button>Go to Dashboard</Button>
    </Link>
  </div>
);

export default NotFound;
