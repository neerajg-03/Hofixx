# Render Deployment Guide for Hofixx

This guide will help you deploy your Hofixx application to Render.

## Prerequisites

1. **MongoDB Atlas Account**: Set up a free MongoDB Atlas cluster
2. **Render Account**: Sign up at [render.com](https://render.com)
3. **Razorpay Account**: For payment processing (if using payments)

## Step 1: Set up MongoDB Atlas

1. Go to [MongoDB Atlas](https://www.mongodb.com/atlas)
2. Create a free cluster
3. Create a database user with read/write permissions
4. Whitelist all IP addresses (0.0.0.0/0) for Render
5. Get your connection string (it will look like: `mongodb+srv://username:password@cluster.mongodb.net/hofix?retryWrites=true&w=majority`)

## Step 2: Deploy to Render

### Option A: Using render.yaml (Recommended)

1. Push your code to GitHub
2. In Render dashboard, click "New +" → "Blueprint"
3. Connect your GitHub repository
4. Render will automatically detect the `render.yaml` file
5. Click "Apply" to deploy

### Option B: Manual Setup

1. In Render dashboard, click "New +" → "Web Service"
2. Connect your GitHub repository
3. Configure the service:
   - **Name**: `hofixx-backend`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python app.py`
   - **Plan**: Free

## Step 3: Environment Variables

Set these environment variables in your Render service:

### Required Variables:
```
FLASK_ENV=production
PORT=10000
SECRET_KEY=<generate-a-secure-secret-key>
JWT_SECRET_KEY=<generate-a-secure-jwt-secret>
MONGODB_URI=<your-mongodb-atlas-connection-string>
```

### Optional Variables:
```
REDIS_URL=<redis-url-if-using-redis>
RAZORPAY_KEY_ID=<your-razorpay-key-id>
RAZORPAY_KEY_SECRET=<your-razorpay-key-secret>
```

## Step 4: Set up Redis (Optional but Recommended)

For better SocketIO performance:

1. In Render dashboard, click "New +" → "Redis"
2. Choose the free plan
3. Copy the Redis URL
4. Set `REDIS_URL` environment variable in your web service

## Step 5: File Uploads

The application stores uploaded files in the `static/uploads/` directory. For production:

1. **Option 1**: Use a cloud storage service (AWS S3, Cloudinary, etc.)
2. **Option 2**: Use Render's persistent disk (paid plans only)
3. **Option 3**: Files will be lost on redeploy (not recommended for production)

## Step 6: Custom Domain (Optional)

1. In your Render service settings, go to "Custom Domains"
2. Add your domain
3. Update DNS records as instructed by Render

## Step 7: SSL/HTTPS

Render automatically provides SSL certificates for all services. Your app will be available at:
- `https://your-service-name.onrender.com`

## Troubleshooting

### Common Issues:

1. **Build Failures**: Check that all dependencies are in `requirements.txt`
2. **Database Connection**: Verify MongoDB Atlas connection string and IP whitelist
3. **Static Files**: Ensure static files are properly configured
4. **WebSocket Issues**: Check Redis configuration for SocketIO

### Logs:
- View logs in Render dashboard under your service
- Check both build logs and runtime logs

## Environment Variables Reference

| Variable | Description | Required | Example |
|----------|-------------|----------|---------|
| `FLASK_ENV` | Flask environment | Yes | `production` |
| `PORT` | Port for the application | Yes | `10000` |
| `SECRET_KEY` | Flask secret key | Yes | `your-secret-key` |
| `JWT_SECRET_KEY` | JWT secret key | Yes | `your-jwt-secret` |
| `MONGODB_URI` | MongoDB connection string | Yes | `mongodb+srv://...` |
| `REDIS_URL` | Redis connection string | No | `redis://...` |
| `RAZORPAY_KEY_ID` | Razorpay key ID | No | `rzp_test_...` |
| `RAZORPAY_KEY_SECRET` | Razorpay key secret | No | `your-secret` |

## Post-Deployment

1. Test all major functionality
2. Set up monitoring and alerts
3. Configure backup strategies for your database
4. Set up CI/CD for automatic deployments

## Support

For issues specific to Render deployment, check:
- [Render Documentation](https://render.com/docs)
- [Render Community](https://community.render.com)
