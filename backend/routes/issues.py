from fastapi import APIRouter, HTTPException, Form, File, UploadFile, Depends
from clients.supabase_client import supabase
from config.settings import SUPABASE_URL
from typing import Optional
from datetime import datetime
import uuid
import os

router = APIRouter()

@router.post("/report-issue")
async def report_issue(
    description: str = Form(...),
    category: str = Form(...),
    intensity: int = Form(...),
    location: str = Form(...),
    user_id: str = Form(None),  # Add user_id parameter
    photo: Optional[UploadFile] = File(None),
    pdf: Optional[UploadFile] = File(None)
):
    try:
        photo_url = None
        pdf_url = None
        
        # Handle photo upload
        if photo:
            # Validate photo
            if not photo.content_type or not photo.content_type.startswith('image/'):
                raise HTTPException(status_code=400, detail="Invalid photo format")
            
            if photo.size and photo.size > 5 * 1024 * 1024:  # 5MB limit
                raise HTTPException(status_code=400, detail="Photo size too large (max 5MB)")
            
            try:
                # Generate unique filename
                file_extension = 'jpg'  # default extension
                if photo.filename and '.' in photo.filename:
                    ext = photo.filename.split('.')[-1].lower()
                    if ext in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
                        file_extension = ext
                photo_filename = f"photos/{uuid.uuid4()}.{file_extension}"
                
                # Read file content
                photo_content = await photo.read()
                
                print(f"Uploading photo to: {photo_filename}")
                
                # Try to upload directly (bucket exists based on our test)
                try:
                        # Upload to Supabase Storage
                        photo_response = supabase.storage.from_("issue-attachments").upload(
                            photo_filename, 
                            photo_content,
                            file_options={"content-type": photo.content_type}
                        )
                        
                        print(f"Photo upload response: {photo_response}")
                        
                        # Upload was successful if we get here (UploadResponse object)
                        print(f"Photo upload successful: {photo_response.path}")
                        
                        # Get public URL
                        photo_url = supabase.storage.from_("issue-attachments").get_public_url(photo_filename)
                        print(f"Generated photo URL: {photo_url}")
                        
                except Exception as storage_error:
                    print(f"Storage error: {storage_error}")
                    print("Skipping photo upload due to storage issues")
                    photo_url = None
                
            except HTTPException:
                raise
            except Exception as upload_error:
                print(f"Photo upload error: {upload_error}")
                print("Skipping photo upload")
                photo_url = None

        # Handle PDF upload
        if pdf:
            # Validate PDF
            if not pdf.content_type or pdf.content_type != 'application/pdf':
                raise HTTPException(status_code=400, detail="Invalid PDF format. Only PDF files are allowed.")
            
            if pdf.size and pdf.size > 10 * 1024 * 1024:  # 10MB limit
                raise HTTPException(status_code=400, detail="PDF size too large (max 10MB)")
            
            try:
                # Generate unique filename
                pdf_filename = f"pdfs/{uuid.uuid4()}.pdf"
                
                # Read file content
                pdf_content = await pdf.read()
                
                # Try to upload directly (bucket exists based on our test)
                try:
                        # Upload to Supabase Storage
                        pdf_response = supabase.storage.from_("issue-attachments").upload(
                            pdf_filename, 
                            pdf_content,
                            file_options={"content-type": "application/pdf"}
                        )
                        
                        print(f"PDF upload response: {pdf_response}")
                        
                        # Upload was successful if we get here (UploadResponse object)
                        print(f"PDF upload successful: {pdf_response.path}")
                        
                        # Get public URL
                        pdf_url = supabase.storage.from_("issue-attachments").get_public_url(pdf_filename)
                        print(f"Generated PDF URL: {pdf_url}")
                        
                except Exception as storage_error:
                    print(f"Storage error: {storage_error}")
                    print("Skipping PDF upload due to storage issues")
                    pdf_url = None
                
            except HTTPException:
                raise
            except Exception as upload_error:
                print(f"PDF upload error: {upload_error}")
                print("Skipping PDF upload")
                pdf_url = None

        # Insert into Supabase table
        issue_data = {
            "title": description[:50] + "..." if len(description) > 50 else description,
            "description": description,
            "category": category,
            "scale": intensity,
            "location": location,
            "photo_url": photo_url,
            "status": "open",
            "dept_id": 1,  # Default department ID - you may need to adjust this
            "upvotes": 0,  # Add default upvotes
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        
        print(f"Attempting to insert issue data: {issue_data}")
        
        try:
            res = supabase.table("issues").insert(issue_data).execute()
            print(f"Database response: {res}")
            
            if hasattr(res, 'error') and res.error:
                print(f"Database insertion error: {res.error}")
                raise HTTPException(status_code=500, detail=f"Database insertion failed: {res.error}")
            
            print(f"Successfully inserted issue: {res.data}")
            
        except Exception as db_error:
            print(f"Database insertion exception: {db_error}")
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"Database insertion failed: {str(db_error)}")
        
        return {
            "message": "Issue reported successfully", 
            "data": res.data,
            "photo_url": photo_url
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in report_issue: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/issues/{issue_id}")
async def get_issue(issue_id: int):
    """Get issue details including file URLs"""
    try:
        result = supabase.table("issues").select("*").eq("id", issue_id).execute()
        
        if not result.data:
            raise HTTPException(status_code=404, detail="Issue not found")
        
        return result.data[0]
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error fetching issue: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching issue: {str(e)}")

@router.get("/issues")
async def get_all_issues():
    """Get all issues"""
    try:
        result = supabase.table("issues").select("*").order("created_at", desc=True).execute()
        return {"issues": result.data}
        
    except Exception as e:
        print(f"Error fetching issues: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching issues: {str(e)}")

@router.delete("/issues/{issue_id}")
async def delete_issue(issue_id: int):
    """Delete issue and associated files"""
    try:
        # Get issue data first
        result = supabase.table("issues").select("*").eq("id", issue_id).execute()
        
        if not result.data:
            raise HTTPException(status_code=404, detail="Issue not found")
        
        issue = result.data[0]
        
        # Delete files from storage if they exist
        if issue.get("photo_url"):
            try:
                # Extract filename from URL
                photo_path = issue["photo_url"].split("/")[-1]
                if "photos/" in issue["photo_url"]:
                    full_path = f"photos/{photo_path}"
                else:
                    full_path = photo_path
                supabase.storage.from_("issue-attachments").remove([full_path])
            except Exception as e:
                print(f"Error deleting photo: {e}")
        
        if issue.get("pdf_url"):
            try:
                # Extract filename from URL
                pdf_path = issue["pdf_url"].split("/")[-1]
                if "pdfs/" in issue["pdf_url"]:
                    full_path = f"pdfs/{pdf_path}"
                else:
                    full_path = pdf_path
                supabase.storage.from_("issue-attachments").remove([full_path])
            except Exception as e:
                print(f"Error deleting PDF: {e}")
        
        # Delete from database
        delete_result = supabase.table("issues").delete().eq("id", issue_id).execute()
        
        if delete_result.error:
            raise HTTPException(status_code=500, detail=f"Database deletion failed: {delete_result.error}")
        
        return {"message": "Issue and associated files deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error deleting issue: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error deleting issue: {str(e)}")